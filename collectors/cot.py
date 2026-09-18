"""CFTC Commitments of Traders: what speculators were actually positioned for, weekly.

EVERY OTHER DATASET HERE IS A PRICE. This one is the only free source for what money DID -
who was long, who was short, and how crowded the trade had become before it moved. A price
tells you the clearing level; positioning tells you who had to be wrong for it to get there.

Two measures per contract:

  net speculative % of OI   Non-commercial longs minus shorts, over total open interest.
                            Normalised on purpose: raw contract counts grow with the market,
                            so a 1995 net long is not comparable to a 2025 one. The share is.
  open interest             How much is at stake at all. A crowded position in a shrinking
                            market is a different animal from the same share in a deep one.

"Non-commercial" is the CFTC's term for traders with no underlying business in the
commodity - funds and speculators. "Commercial" is the hedger side, and by construction
the two roughly mirror each other, so only the speculative side is emitted.

WHY THE LEGACY REPORT: the newer disaggregated and financial-trader reports start in 2006.
The legacy futures-only report runs from 1986, which covers three recessions and two
commodity supercycles instead of one. Breadth of history beats granularity of trader class
for this repo's purpose.

CAVEAT WORTH STATING: positioning is reported as of Tuesday and published Friday. Any
analysis that uses it as of Tuesday is using information nobody had until Friday. The
report_date here is the Tuesday, so shift it forward three days before joining to prices.

Licence: US federal work, public domain. https://publicreporting.cftc.gov/
"""
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from urllib.parse import quote

import pandas as pd

from .common import fetch, write

RESOURCE = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
FIELDS = ("report_date_as_yyyy_mm_dd,contract_market_name,commodity_name,open_interest_all,"
          "noncomm_positions_long_all,noncomm_positions_short_all")

# commodity_name -> (label, group). Chosen for breadth across what moves: currencies,
# metals, energy, softs, rates, equity. Electricity and pollution are excluded despite being
# the largest row counts - they are hundreds of tiny regional contracts, not one market.
WANTED = {
    "SWISS FRANC": ("CHF", "fx"),
    "JAPANESE YEN": ("JPY", "fx"),
    "POUND STERLING": ("GBP", "fx"),
    "CANADIAN DOLLAR": ("CAD", "fx"),
    "U.S. DOLLAR INDEX": ("USD index", "fx"),
    "GOLD": ("Gold", "metals"),
    "SILVER": ("Silver", "metals"),
    "COPPER": ("Copper", "metals"),
    "PLATINUM": ("Platinum", "metals"),
    "CRUDE OIL": ("Crude oil", "energy"),
    "NATURAL GAS": ("Natural gas", "energy"),
    "HEATING OIL-DIESEL-GASOIL": ("Heating oil", "energy"),
    "GASOLINE": ("Gasoline", "energy"),
    "WHEAT": ("Wheat", "ags"),
    "CORN": ("Corn", "ags"),
    "SOYBEANS": ("Soybeans", "ags"),
    "SUGAR": ("Sugar", "ags"),
    "COFFEE": ("Coffee", "ags"),
    "COCOA": ("Cocoa", "ags"),
    "COTTON": ("Cotton", "ags"),
    "LIVE CATTLE": ("Live cattle", "ags"),
    "LEAN HOGS": ("Lean hogs", "ags"),
    "T-BONDS": ("US T-bonds", "rates"),
    "T-NOTES, 6.5-10 YEAR": ("US 10-year notes", "rates"),
    "EURODOLLARS": ("Eurodollars", "rates"),
    "S&P BROAD BASED STOCK INDICES": ("S&P 500", "equity"),
    "NASDAQ  BROADBASED INDICES": ("Nasdaq", "equity"),
    "DOW JONES BROAD BASED INDICES": ("Dow Jones", "equity"),
    "RUSSELL INDEX": ("Russell", "equity"),
    "NIKKEI STOCK AVERAGE": ("Nikkei", "equity"),
}


def _one(item):
    name, (label, group) = item
    # quote() matters: "S&P BROAD BASED STOCK INDICES" contains an ampersand, which ends the
    # query parameter early and returns a 400 rather than an error anyone would notice.
    where = quote(f"commodity_name='{name}'", safe="")
    q = (f"{RESOURCE}?$select={quote(FIELDS, safe=',')}&$where={where}"
         f"&$order=report_date_as_yyyy_mm_dd&$limit=200000")
    try:
        d = pd.read_json(StringIO(fetch(q, binary=False)))
    except Exception as e:
        return label, None, type(e).__name__
    if d.empty:
        return label, None, "no rows"

    # One commodity spans several contracts (full size, mini, different exchanges). Taking
    # the most-reported one keeps a single continuous series instead of silently summing
    # contracts with different multipliers.
    main = d["contract_market_name"].value_counts().idxmax()
    d = d[d["contract_market_name"] == main].copy()

    oi = pd.to_numeric(d["open_interest_all"], errors="coerce")
    lng = pd.to_numeric(d["noncomm_positions_long_all"], errors="coerce")
    srt = pd.to_numeric(d["noncomm_positions_short_all"], errors="coerce")
    date = pd.to_datetime(d["report_date_as_yyyy_mm_dd"], errors="coerce")
    ok = date.notna() & oi.notna() & lng.notna() & srt.notna() & (oi > 0)
    if ok.sum() < 100:
        return label, None, f"only {int(ok.sum())} usable rows"

    net_pct = (lng[ok] - srt[ok]) / oi[ok] * 100
    base = dict(date=date[ok].dt.strftime("%Y-%m-%d"), group=group, contract=main)
    out = pd.concat([
        pd.DataFrame({**base, "series": f"{label}: net speculative %OI",
                      "value": net_pct, "unit": "percent of open interest"}),
        pd.DataFrame({**base, "series": f"{label}: open interest",
                      "value": oi[ok], "unit": "contracts"}),
    ], ignore_index=True)
    return label, out, None


def collect(workers=6):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(_one, WANTED.items()))
    frames, dropped = [], []
    for label, df, why in results:
        (frames.append(df) if df is not None else dropped.append((label, why)))
    for label, why in dropped:
        print(f"  ! dropped COT {label}: {why}")
    assert len(frames) >= 20, f"only {len(frames)} COT contracts usable"

    out = pd.concat(frames, ignore_index=True).sort_values(["series", "date"])
    pct = out[out["series"].str.endswith("%OI")]["value"]
    # Longs minus shorts over open interest cannot exceed 100% in either direction. If it
    # does, the wrong column got divided and the whole dataset is nonsense.
    assert pct.between(-100, 100).all(), f"net %OI out of range: {pct.min():.1f}..{pct.max():.1f}"
    return write("cftc_positioning", out,
                 source=f"{RESOURCE} (legacy futures-only report)",
                 licence="US federal work, public domain. Attribute the CFTC.",
                 note=("Weekly speculative positioning, 1986 onwards. Net non-commercial "
                       "longs minus shorts as a share of open interest, plus open interest "
                       "itself. Positioning is as of TUESDAY but published Friday - shift "
                       "the date forward three days before joining it to prices, or you are "
                       "trading on information nobody had yet. One contract per commodity "
                       "(the most-reported one), named in the `contract` column."))


if __name__ == "__main__":
    collect()
