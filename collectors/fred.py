"""Macro and market series from FRED, organised by how they reach asset prices.

The point of this repo is correlating market behaviour with what happens in the world, so
the series here are chosen by TRANSMISSION CHANNEL rather than by topic. Each group is a
distinct route from an event to a price:

  fx          the price of money against other money
  rates       the risk-free curve - what every other asset is discounted against
  credit      spreads and stress indices - how willing anyone is to lend
  liquidity   money supply and the central bank balance sheet
  inflation   realised and, more usefully, market-IMPLIED (breakevens, real yields)
  activity    the real economy - jobs, output, sentiment
  housing     the largest asset most households own
  trade       cross-border flows and the balance
  equity      index levels, for the thing being explained
  commodity   physical inputs that show up in costs
  uncertainty policy and equity-market uncertainty indices

Breakevens (T10YIE) and real yields (DFII10) matter more than CPI for this purpose: they are
what the market *expects*, priced continuously, not what a statistical agency measured two
months ago.

STALENESS IS CHECKED, NOT ASSUMED. Several FRED series still resolve long after they stopped
publishing - TEDRATE ends in 2022 and would silently look like a flat line to 2026. Anything
whose last observation is older than STALE_DAYS is dropped with a printed note.

Licence: FRED series are redistributed from their original sources. Most are US federal
works (public domain); ICE BofA spread indices carry ICE's terms. Attribute FRED and check
the individual series page before commercial redistribution.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd

from .common import fetch, write

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1900-01-01"
STALE_DAYS = 400          # generous: quarterly series routinely lag two quarters

# series id -> (label, channel, unit)
SERIES = {
    # --- fx: the price of money -------------------------------------------------
    "DEXUSEU": ("USD per EUR", "fx", "USD per EUR"),
    "DEXUSUK": ("USD per GBP", "fx", "USD per GBP"),
    "DEXJPUS": ("JPY per USD", "fx", "JPY per USD"),
    "DEXSZUS": ("CHF per USD", "fx", "CHF per USD"),
    "DEXCHUS": ("CNY per USD", "fx", "CNY per USD"),
    "DEXCAUS": ("CAD per USD", "fx", "CAD per USD"),
    "DEXUSAL": ("USD per AUD", "fx", "USD per AUD"),
    "DEXKOUS": ("KRW per USD", "fx", "KRW per USD"),
    "DEXMXUS": ("MXN per USD", "fx", "MXN per USD"),
    "DEXBZUS": ("BRL per USD", "fx", "BRL per USD"),
    "DEXINUS": ("INR per USD", "fx", "INR per USD"),
    "DTWEXBGS": ("USD broad index", "fx", "index"),
    # --- rates: the discount curve ----------------------------------------------
    "DFF": ("Fed funds effective", "rates", "percent"),
    "DGS3MO": ("US 3-month yield", "rates", "percent"),
    "DGS2": ("US 2-year yield", "rates", "percent"),
    "DGS5": ("US 5-year yield", "rates", "percent"),
    "DGS10": ("US 10-year yield", "rates", "percent"),
    "DGS30": ("US 30-year yield", "rates", "percent"),
    "T10Y2Y": ("10y minus 2y spread", "rates", "percentage points"),
    "T10Y3M": ("10y minus 3m spread", "rates", "percentage points"),
    # --- credit: willingness to lend --------------------------------------------
    "BAMLH0A0HYM2": ("US high-yield OAS", "credit", "percentage points"),
    "BAMLC0A0CM": ("US investment-grade OAS", "credit", "percentage points"),
    "STLFSI4": ("St. Louis financial stress", "credit", "index"),
    "NFCI": ("Chicago financial conditions", "credit", "index"),
    # --- liquidity ---------------------------------------------------------------
    "M2SL": ("US M2 money supply", "liquidity", "USD billions"),
    "BOGMBASE": ("US monetary base", "liquidity", "USD millions"),
    "WALCL": ("Fed total assets", "liquidity", "USD millions"),
    "RRPONTSYD": ("Overnight reverse repo", "liquidity", "USD billions"),
    "WTREGEN": ("Treasury General Account", "liquidity", "USD millions"),
    # --- inflation: realised and market-implied ----------------------------------
    "CPIAUCSL": ("US CPI", "inflation", "index"),
    "CPILFESL": ("US core CPI", "inflation", "index"),
    "CORESTICKM159SFRBATL": ("Sticky CPI", "inflation", "percent per year"),
    "T10YIE": ("10y inflation breakeven", "inflation", "percent"),
    "T5YIE": ("5y inflation breakeven", "inflation", "percent"),
    "DFII10": ("10y real yield (TIPS)", "inflation", "percent"),
    # --- activity ----------------------------------------------------------------
    "UNRATE": ("US unemployment rate", "activity", "percent"),
    "PAYEMS": ("US nonfarm payrolls", "activity", "thousands of persons"),
    "INDPRO": ("US industrial production", "activity", "index"),
    "ICSA": ("Initial jobless claims", "activity", "persons"),
    "UMCSENT": ("Consumer sentiment", "activity", "index"),
    "RECPROUSM156N": ("Recession probability", "activity", "percent"),
    "GDPC1": ("US real GDP", "activity", "USD billions"),
    # --- housing -----------------------------------------------------------------
    "CSUSHPINSA": ("US house prices (Case-Shiller)", "housing", "index"),
    "HOUST": ("US housing starts", "housing", "thousands of units"),
    "MORTGAGE30US": ("US 30-year mortgage rate", "housing", "percent"),
    # --- trade -------------------------------------------------------------------
    "BOPGSTB": ("US trade balance", "trade", "USD millions"),
    "GFDEGDQ188S": ("US federal debt to GDP", "trade", "percent of GDP"),
    # --- equity: the thing being explained ---------------------------------------
    "SP500": ("S&P 500 index", "equity", "index"),
    "NASDAQCOM": ("Nasdaq Composite", "equity", "index"),
    "DJIA": ("Dow Jones Industrial", "equity", "index"),
    "VIXCLS": ("VIX", "equity", "index"),
    "WILL5000IND": ("Wilshire 5000", "equity", "index"),
    # --- commodity ----------------------------------------------------------------
    "DCOILWTICO": ("WTI crude spot", "commodity", "USD per barrel"),
    "DCOILBRENTEU": ("Brent crude spot", "commodity", "USD per barrel"),
    "DHHNGSP": ("Henry Hub natural gas", "commodity", "USD per mmbtu"),
    # --- uncertainty ---------------------------------------------------------------
    "USEPUINDXD": ("US economic policy uncertainty", "uncertainty", "index"),
    "WLEMUINDXD": ("US equity market uncertainty", "uncertainty", "index"),
}


def _one(sid):
    label, channel, unit = SERIES[sid]
    try:
        raw = fetch(URL.format(sid=sid), binary=False)
        d = pd.read_csv(pd.io.common.StringIO(raw))
    except Exception as e:
        return sid, None, f"{type(e).__name__}"
    dcol = "observation_date" if "observation_date" in d.columns else d.columns[0]
    vcol = next((c for c in d.columns if c != dcol), None)
    if vcol is None:
        return sid, None, "no value column"
    out = pd.DataFrame({
        "date": pd.to_datetime(d[dcol], errors="coerce"),
        "value": pd.to_numeric(d[vcol], errors="coerce"),
    }).dropna()
    if len(out) < 20:
        return sid, None, f"only {len(out)} observations"
    last = out["date"].max().date()
    if last < date.today() - timedelta(days=STALE_DAYS):
        return sid, None, f"stale, last {last}"
    out["series"] = label
    out["channel"] = channel
    out["unit"] = unit
    out["fred_id"] = sid
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return sid, out[["date", "series", "channel", "value", "unit", "fred_id"]], None


def collect(workers=8):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(_one, SERIES))
    frames, dropped = [], []
    for sid, df, why in results:
        (frames if df is not None else dropped).append(df if df is not None else (sid, why))
    for sid, why in dropped:
        print(f"  ! dropped {sid}: {why}")
    assert len(frames) >= 40, f"only {len(frames)} series usable - FRED may have changed"
    out = pd.concat(frames, ignore_index=True).sort_values(["channel", "series", "date"])
    return write("market_drivers", out,
                 source="https://fred.stlouisfed.org (see fred_id per row)",
                 licence=("Mostly US federal works (public domain); ICE BofA spread indices "
                          "carry ICE terms. Attribute FRED."),
                 note=("Macro and market series grouped by transmission channel: fx, rates, "
                       "credit, liquidity, inflation, activity, housing, trade, equity, "
                       "commodity, uncertainty. Use the channel column to filter. Series "
                       "that stopped publishing are dropped, not carried forward flat."))


if __name__ == "__main__":
    collect()
