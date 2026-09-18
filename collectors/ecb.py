"""Euro area rates, curve and FX from the ECB Data Portal - no key, no registration.

WHY THIS EXISTS: market_drivers is FRED, and FRED's free non-US coverage is thin, so the
rates, credit and activity channels there are all US. That makes every cross-asset question
implicitly a question about America. This is the other half of the developed-market plumbing.

The `channel` column matches fred.py's on purpose, so the two datasets concatenate:

    us = pd.read_csv("data/market_drivers.csv")
    eu = pd.read_csv("data/euro_area_drivers.csv")
    both = pd.concat([us, eu])[lambda d: d.channel == "rates"]

Three things worth knowing about the source:

  The SDMX REST API speaks CSV directly with `?format=csvdata`, so no XML parsing.
  ECB FX rates are EUR-BASED and published once a day around 16:00 CET. They are reference
  rates, not tradeable quotes - fine for "what happened", wrong for backtesting a spread.
  RUB stops in March 2022 when the ECB suspended publication. That is a real event, not a
  gap to fill, so it is left ending where it ends.

Licence: free to use with attribution to the ECB. https://data.ecb.europa.eu/
"""
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

import pandas as pd

from .common import fetch, write

API = "https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=csvdata"

# EUR reference rates. The ECB quotes units of currency per EUR.
FX = ["USD", "JPY", "GBP", "CHF", "SEK", "NOK", "DKK", "CAD", "AUD", "NZD", "CNY", "HKD",
      "SGD", "KRW", "INR", "BRL", "MXN", "ZAR", "TRY", "PLN", "CZK", "HUF", "RON", "BGN",
      "ILS", "IDR", "MYR", "PHP", "THB", "ISK", "RUB"]

# (flow, key) -> (label, channel, unit)
SERIES = {
    ("FM", "D.U2.EUR.4F.KR.MRR_FR.LEV"): ("ECB main refinancing rate", "rates", "percent"),
    ("FM", "D.U2.EUR.4F.KR.DFR.LEV"): ("ECB deposit facility rate", "rates", "percent"),
    ("FM", "D.U2.EUR.4F.KR.MLFR.LEV"): ("ECB marginal lending rate", "rates", "percent"),
    ("FM", "M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA"): ("Euribor 3-month", "rates", "percent"),
    ("FM", "M.U2.EUR.4F.MM.EONIA.HSTA"): ("EONIA overnight", "rates", "percent"),
    ("EST", "B.EU000A2X2A25.WT"): ("Euro short-term rate (ESTR)", "rates", "percent"),
    ("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_1Y"): ("Euro area AAA 1-year yield", "rates", "percent"),
    ("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"): ("Euro area AAA 2-year yield", "rates", "percent"),
    ("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_5Y"): ("Euro area AAA 5-year yield", "rates", "percent"),
    ("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"): ("Euro area AAA 10-year yield", "rates", "percent"),
    ("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_30Y"): ("Euro area AAA 30-year yield", "rates", "percent"),
    ("ICP", "M.U2.N.000000.4.ANR"): ("Euro area HICP inflation", "inflation", "percent per year"),
    ("ICP", "M.U2.N.XEF000.4.ANR"): ("Euro area core HICP inflation", "inflation", "percent per year"),
    ("BSI", "M.U2.Y.V.M30.X.I.U2.2300.Z01.A"): ("Euro area M3 growth", "liquidity", "percent per year"),
    ("BSI", "M.U2.Y.V.M10.X.I.U2.2300.Z01.A"): ("Euro area M1 growth", "liquidity", "percent per year"),
    ("LFSI", "M.I9.S.UNEHRT.TOTAL0.15_74.T"): ("Euro area unemployment rate", "activity", "percent"),
}
for _c in FX:
    SERIES[("EXR", f"D.{_c}.EUR.SP00.A")] = (f"{_c} per EUR", "fx", f"{_c} per EUR")


def _one(item):
    (flow, key), (label, channel, unit) = item
    try:
        raw = fetch(API.format(flow=flow, key=key), binary=False)
        d = pd.read_csv(StringIO(raw))
    except Exception as e:
        return label, None, type(e).__name__
    if "TIME_PERIOD" not in d.columns or "OBS_VALUE" not in d.columns:
        return label, None, "unexpected columns"
    out = pd.DataFrame({
        "date": pd.to_datetime(d["TIME_PERIOD"], errors="coerce"),
        "value": pd.to_numeric(d["OBS_VALUE"], errors="coerce"),
    }).dropna()
    if len(out) < 20:
        return label, None, f"only {len(out)} observations"
    out["series"] = label
    out["channel"] = channel
    out["unit"] = unit
    out["ecb_key"] = f"{flow}/{key}"
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return label, out[["date", "series", "channel", "value", "unit", "ecb_key"]], None


def collect(workers=8):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(_one, SERIES.items()))
    frames, dropped = [], []
    for label, df, why in results:
        (frames.append(df) if df is not None else dropped.append((label, why)))
    for label, why in dropped:
        print(f"  ! dropped {label}: {why}")
    assert len(frames) >= 30, f"only {len(frames)} ECB series usable - API may have changed"

    out = pd.concat(frames, ignore_index=True).sort_values(["channel", "series", "date"])
    # Policy rates went negative in 2014 and the curve followed. A sign flip here would be
    # invisible on a chart but would reverse every correlation, so assert the era exists.
    dfr = out[out["series"] == "ECB deposit facility rate"]["value"]
    assert dfr.min() < 0, "deposit facility never negative - sign or scaling is wrong"
    assert out["value"].abs().max() < 1e5, "implausible magnitude in ECB data"
    return write("euro_area_drivers", out,
                 source="https://data-api.ecb.europa.eu/service/data/ (see ecb_key per row)",
                 licence="Free use with attribution to the European Central Bank.",
                 note=("Euro area policy rates, AAA yield curve, HICP, M3, unemployment and "
                       "daily EUR reference FX for 31 currencies. The `channel` column "
                       "matches market_drivers so the two concatenate. FX is EUR-based and "
                       "quoted once daily - reference rates, not tradeable quotes. RUB ends "
                       "in March 2022 when the ECB suspended publication."))


if __name__ == "__main__":
    collect()
