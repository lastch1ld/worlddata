"""Build one monthly panel out of every worlddata dataset that has a time series.

Everything downstream works on this panel. Two rules decide correctness here:

1. Monthly aggregation uses the LAST observation in the month, not the mean.
   A monthly average of daily prices manufactures autocorrelation (~+0.27 AR(1)
   on an index whose true month-end AR(1) is ~+0.10) and makes every lead/lag
   test look predictive when it is not. The only exceptions are indices that are
   themselves defined as period intensities (GPR), where the mean is the meaning.

2. Levels are almost all non-stationary, so analysis runs on CHANGES:
   log-differences for anything price-like and strictly positive, first
   differences for rates, spreads and things that can go negative.
"""
import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# units whose series are already a rate/level in percent-space -> first difference
DIFF_UNITS = {
    "percent", "percentage points", "percent per year", "percent of GDP",
    "standard deviations from average", "ratio",
}
# indices that can be negative, so a log-difference is undefined
DIFF_EXTRA = {
    "Chicago financial conditions", "St. Louis financial stress",
    "Supply chain pressure", "US trade balance",
}


def _monthly(df, how="last", key="series", val="value"):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    g = df.groupby([pd.Grouper(freq="ME"), key])[val]
    return (g.last() if how == "last" else g.mean()).unstack(key)


def _csv(name):
    return pd.read_csv(DATA / f"{name}.csv")


def build():
    """Return (levels, changes, units) monthly DataFrames indexed by month end."""
    md = _csv("market_drivers")
    units = md.drop_duplicates("series").set_index("series")["unit"].to_dict()
    lv = _monthly(md)

    # --- geopolitical risk: an intensity index, monthly mean is the definition
    g = _csv("geopolitical_risk_daily")
    for src, dst in [("Geopolitical risk (daily)", "Geopolitical risk"),
                     ("Geopolitical threats (daily)", "Geopolitical threats"),
                     ("Geopolitical acts (daily)", "Geopolitical acts")]:
        sub = g[g.series == src]
        if len(sub):
            lv[dst] = _monthly(sub, how="mean").iloc[:, 0]
            units[dst] = "index"

    # --- market series with longer history than the FRED mirrors
    lv["VIX"] = _monthly(_csv("vix_daily"))["vix_close"]
    units["VIX"] = "index"
    lv["Gold"] = _monthly(_csv("gold_monthly"))["gold"]
    units["Gold"] = "USD"
    lv["Brent (long)"] = _monthly(_csv("oil_brent_daily"))["brent"]
    units["Brent (long)"] = "USD"
    lv["WTI (long)"] = _monthly(_csv("oil_wti_daily")).iloc[:, 0]
    units["WTI (long)"] = "USD"

    cr = _csv("crypto_daily")
    for name in cr.series.unique():
        tag = name.split(" (")[0]
        if tag in {"Bitcoin", "Ethereum"}:
            lv[tag] = _monthly(cr[cr.series == name]).iloc[:, 0]
            units[tag] = "USD"

    spm = _monthly(_csv("sp500_monthly"))
    # Shiller's SP500 is a monthly AVERAGE of daily closes: keep it for valuation
    # and long-history context, never for lead/lag. Flagged in the name.
    for src, dst in [("SP500", "S&P (Shiller avg)"), ("PE10", "S&P PE10"),
                     ("Real Earnings", "S&P real earnings"),
                     ("Real Dividend", "S&P real dividend")]:
        lv[dst] = spm[src]
        units[dst] = "ratio" if dst == "S&P PE10" else "index"

    lv["Supply chain pressure"] = _monthly(_csv("supply_chain_pressure")).iloc[:, 0]
    units["Supply chain pressure"] = "standard deviations from average"

    # --- uncertainty family
    epu = _csv("uncertainty_epu")
    for scope in epu.scope.unique():
        sub = epu[epu.scope == scope]
        col = f"EPU {scope}"
        s = _monthly(sub, how="mean").mean(axis=1)
        if s.notna().sum() >= 100:
            lv[col] = s
            units[col] = "index"

    wui = _csv("uncertainty_world")
    for scope in ["USA", "CHN", "DEU", "GBR", "JPN", "RUS"]:
        sub = wui[wui.scope == scope]
        if len(sub):
            s = _monthly(sub, how="mean").mean(axis=1)
            # WUI is quarterly-stamped; forward fill inside the quarter
            lv[f"WUI {scope}"] = s.reindex(lv.index).ffill(limit=2)
            units[f"WUI {scope}"] = "index"

    tpu = _csv("trade_policy_uncertainty")
    for name in tpu.series.unique():
        sub = tpu[(tpu.series == name) & (tpu.scope == "US")]
        if len(sub) >= 100:
            col = f"TPU {name.split(' (')[0]}"
            lv[col] = _monthly(sub, how="mean").iloc[:, 0]
            units[col] = "count"

    # --- speculative positioning (CFTC net non-commercial, % of open interest)
    cft = _csv("cftc_positioning")
    for name in cft.series.unique():
        if "net speculative %OI" not in name:
            continue
        col = "POS " + name.split(":")[0]
        s = _monthly(cft[cft.series == name])[name]
        if s.notna().sum() >= 100:
            lv[col] = s
            units[col] = "percent"

    # --- euro area, for a non-US cross-check
    ea = _csv("euro_area_drivers")
    keep = ["Euro area unemployment rate", "Euro area HICP",
            "Euro area industrial production", "Euro area M3"]
    eam = _monthly(ea)
    eu_units = ea.drop_duplicates("series").set_index("series")["unit"].to_dict()
    for name in keep:
        if name in eam.columns:
            lv[name] = eam[name]
            units[name] = eu_units.get(name, "index")

    lv = lv.sort_index()
    lv = lv.loc[:, lv.notna().sum() >= 60]

    cols = {}
    for c in lv.columns:
        s = lv[c]
        if units.get(c) in DIFF_UNITS or c in DIFF_EXTRA:
            cols[c] = s.diff()
        else:
            cols[c] = np.log(s.where(s > 0)).diff()
    ch = pd.DataFrame(cols, index=lv.index).replace([np.inf, -np.inf], np.nan)
    return lv, ch, units


# The only long month-end equity series in the repo. FRED's SP500/DJIA mirrors are
# truncated to a rolling 10 years and Shiller's is month-averaged, so Nasdaq
# Composite (1971-, month-end) is what every equity test below actually uses.
EQUITY = "Nasdaq Composite"

if __name__ == "__main__":
    lv, ch, units = build()
    print(f"{lv.shape[1]} series, {lv.shape[0]} months, "
          f"{lv.index.min():%Y-%m} to {lv.index.max():%Y-%m}")
    print(f"equity proxy {EQUITY}: AR(1)={ch[EQUITY].autocorr(1):+.3f}")
