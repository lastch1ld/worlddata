"""Full correlation / causality / predictability sweep over the worlddata panel.

Writes CSV tables to findings/tables, PNG charts to findings/charts, and a
machine-readable findings/summary.json. The prose report in findings/README.md
is written from these outputs.

Run:  .venv/Scripts/python.exe findings/run_analysis.py
"""
import itertools
import json
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial.distance import squareform
from scipy import stats as sps
from sklearn.decomposition import PCA
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import adfuller, coint, kpss

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel
import stats_core as sc

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
TAB = HERE / "tables"
CHT = HERE / "charts"
TAB.mkdir(exist_ok=True)
CHT.mkdir(exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 130, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": "white",
})

LV, CH, UNITS = panel.build()
EQ = panel.EQUITY
OUT = {}

# A curated core used for the expensive tests. Everything here has >=150 monthly
# observations and is economically interpretable; the all-pairs scans still run
# over the full panel.
CORE = [
    EQ, "VIX", "US 10-year yield", "US 2-year yield", "US 3-month yield",
    "10y minus 2y spread", "10y minus 3m spread", "10y inflation breakeven",
    "10y real yield (TIPS)", "USD broad index", "USD per EUR", "JPY per USD",
    "CAD per USD", "MXN per USD", "Brent (long)", "WTI (long)", "Gold",
    "Bitcoin", "Henry Hub natural gas", "US CPI", "US core CPI", "Sticky CPI",
    "US unemployment rate", "US nonfarm payrolls", "US industrial production",
    "Initial jobless claims", "US housing starts", "US house prices (Case-Shiller)",
    "Consumer sentiment", "US M2 money supply", "Fed total assets",
    "Fed funds effective", "Recession probability", "Chicago financial conditions",
    "St. Louis financial stress", "US economic policy uncertainty",
    "US equity market uncertainty", "Geopolitical risk", "Geopolitical threats",
    "Geopolitical acts", "Supply chain pressure", "POS S&P 500", "POS Gold",
    "POS Crude oil", "POS US 10-year notes", "POS USD index", "S&P PE10",
]
CORE = [c for c in CORE if c in CH.columns]


def save(df, name):
    df.to_csv(TAB / f"{name}.csv", index=False)
    return df


def fig(name):
    plt.tight_layout()
    plt.savefig(CHT / f"{name}.png", bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------- 1. coverage
def section_coverage():
    rows = []
    for c in LV.columns:
        s = LV[c].dropna()
        rows.append({
            "series": c, "unit": UNITS.get(c, ""), "n_months": len(s),
            "start": s.index.min().date(), "end": s.index.max().date(),
            "transform": "diff" if (UNITS.get(c) in panel.DIFF_UNITS
                                    or c in panel.DIFF_EXTRA) else "log-diff",
        })
    df = save(pd.DataFrame(rows).sort_values("n_months"), "01_coverage")
    truncated = df[(pd.to_datetime(df.end).dt.year >= 2025) & (df.n_months < 200)]
    OUT["panel"] = {"series": int(LV.shape[1]), "months": int(LV.shape[0]),
                    "start": str(LV.index.min().date()), "end": str(LV.index.max().date())}
    OUT["truncated_series"] = truncated[["series", "n_months", "start"]].to_dict("records")
    return df


# ----------------------------------------------------- 2. stationarity checks
def section_stationarity():
    rows = []
    for c in CORE:
        for label, s in [("level", LV[c].dropna()), ("change", CH[c].dropna())]:
            s = s.iloc[-600:]
            if len(s) < 60:
                continue
            try:
                adf_p = adfuller(s, autolag="AIC")[1]
            except Exception:
                adf_p = np.nan
            try:
                kpss_p = kpss(s, regression="c", nlags="auto")[1]
            except Exception:
                kpss_p = np.nan
            rows.append({"series": c, "form": label, "n": len(s),
                         "adf_p": adf_p, "kpss_p": kpss_p,
                         "stationary": bool(adf_p < 0.05 and kpss_p > 0.05)})
    df = save(pd.DataFrame(rows), "02_stationarity")
    lev = df[df.form == "level"]
    chg = df[df.form == "change"]
    OUT["stationarity"] = {
        "levels_stationary": int(lev.stationary.sum()), "levels_tested": int(len(lev)),
        "changes_stationary": int(chg.stationary.sum()), "changes_tested": int(len(chg)),
    }
    return df


# ------------------------------------------------- 3. spurious levels vs changes
def section_spurious():
    pairs = [(EQ, "US CPI"), (EQ, "US M2 money supply"), (EQ, "Gold"),
             ("Gold", "US CPI"), ("Bitcoin", "Fed total assets"),
             ("Gold", "US federal debt to GDP"), (EQ, "US nonfarm payrolls"),
             ("Brent (long)", "US M2 money supply"), (EQ, "US house prices (Case-Shiller)")]
    rows = []
    for a, b in pairs:
        if a not in LV or b not in LV:
            continue
        dl = pd.concat([LV[a], LV[b]], axis=1).dropna()
        dc = pd.concat([CH[a], CH[b]], axis=1).dropna()
        if len(dl) < 60 or len(dc) < 60:
            continue
        rl = dl.iloc[:, 0].corr(dl.iloc[:, 1])
        hc = sc.hac_corr(CH[a], CH[b])
        rows.append({"x": a, "y": b, "n_levels": len(dl), "r_levels": rl,
                     "n_changes": len(dc), "r_changes": hc[0] if hc else np.nan,
                     "hac_t_changes": hc[1] if hc else np.nan,
                     "hac_p_changes": hc[2] if hc else np.nan})
    df = save(pd.DataFrame(rows), "03_levels_vs_changes")
    OUT["spurious"] = df.round(4).to_dict("records")

    plt.figure(figsize=(7, 3.6))
    x = np.arange(len(df))
    plt.bar(x - 0.2, df.r_levels, 0.4, label="correlation of levels", color="#c44")
    plt.bar(x + 0.2, df.r_changes, 0.4, label="correlation of monthly changes", color="#357")
    plt.xticks(x, [f"{r.x}\nvs {r.y}" for r in df.itertuples()], rotation=40,
               ha="right", fontsize=6.5)
    plt.axhline(0, color="k", lw=0.8)
    plt.ylabel("Pearson r")
    plt.title("Levels manufacture correlation; changes remove it")
    plt.legend(fontsize=7)
    fig("01_levels_vs_changes")
    return df


# ------------------------------------------- 4. all-pairs contemporaneous scan
def section_contemporaneous(min_n=100):
    cols = [c for c in CH.columns if CH[c].notna().sum() >= min_n]
    rows = []
    for a, b in itertools.combinations(cols, 2):
        d = pd.concat([CH[a], CH[b]], axis=1).dropna()
        n = len(d)
        if n < min_n:
            continue
        r = d.iloc[:, 0].corr(d.iloc[:, 1])
        if not np.isfinite(r):
            continue
        rho = sps.spearmanr(d.iloc[:, 0], d.iloc[:, 1]).statistic
        t = r * np.sqrt(n - 2) / np.sqrt(max(1e-12, 1 - r * r))
        rows.append({"x": a, "y": b, "n": n, "r": r, "spearman": rho,
                     "t_ols": t, "p_ols": 2 * sps.t.sf(abs(t), n - 2)})
    df = pd.DataFrame(rows)
    rej, adj = sc.fdr(df.p_ols)
    df["p_fdr"] = adj
    df["sig_fdr"] = rej
    df["abs_r"] = df.r.abs()
    df = df.sort_values("abs_r", ascending=False).reset_index(drop=True)

    # HAC-verify the top of the list: OLS p-values over-state significance here
    hac = []
    for row in df.head(200).itertuples():
        h = sc.hac_corr(CH[row.x], CH[row.y])
        hac.append((h[1], h[2]) if h else (np.nan, np.nan))
    df["hac_t"] = np.nan
    df["hac_p"] = np.nan
    df.loc[: len(hac) - 1, "hac_t"] = [h[0] for h in hac]
    df.loc[: len(hac) - 1, "hac_p"] = [h[1] for h in hac]

    # Some series in the repo are the same underlying data arriving through two
    # collectors (WTI via FRED and via the oil dataset), or eight variants of one
    # index (the TPU family). At |r| >= 0.95 on monthly changes they carry no
    # independent information, so they are flagged and kept out of the headline
    # list -- and reported separately as a data-quality finding.
    df["near_duplicate"] = df.abs_r >= 0.95
    save(df, "04_contemporaneous_all_pairs")

    dup = df[df.near_duplicate]
    G = nx.Graph()
    G.add_nodes_from(cols)
    G.add_edges_from(zip(dup.x, dup.y))
    groups = [sorted(g) for g in nx.connected_components(G) if len(g) > 1]
    save(pd.DataFrame([{"group": i + 1, "series": s}
                       for i, g in enumerate(groups) for s in g]), "16_redundant_groups")
    OUT["redundancy"] = {
        "pairs_over_0.95": int(len(dup)),
        "groups": groups,
        "series_in_groups": int(sum(len(g) for g in groups)),
        "effective_independent_series": int(len(cols) - sum(len(g) - 1 for g in groups)),
        "series_scanned": int(len(cols)),
    }

    clean = df[~df.near_duplicate]
    OUT["contemporaneous"] = {
        "pairs_tested": int(len(df)),
        "sig_fdr": int(df.sig_fdr.sum()),
        "expected_false_at_p05": round(float(len(df)) * 0.05, 1),
        "top": clean.head(40)[["x", "y", "n", "r", "spearman", "hac_t", "hac_p"]]
               .round(4).to_dict("records"),
    }
    return df


# ---------------------------------------- 5. clustering of the core correlation
def section_clusters():
    X = CH[CORE].loc["1990":]
    C = X.corr(min_periods=80)
    C = C.dropna(how="all").dropna(axis=1, how="all")
    C = C.fillna(0.0)
    M = C.to_numpy(float).copy()
    np.fill_diagonal(M, 1.0)
    C = pd.DataFrame(M, index=C.index, columns=C.columns)
    D = np.clip(1 - M, 0, 2)
    np.fill_diagonal(D, 0.0)
    Z = linkage(squareform(D, checks=False), method="average")
    order = dendrogram(Z, no_plot=True, labels=list(C.columns))["ivl"]
    labels = fcluster(Z, t=6, criterion="maxclust")
    clus = pd.DataFrame({"series": C.columns, "cluster": labels}).sort_values("cluster")
    save(clus, "05_clusters")
    OUT["clusters"] = {int(k): v.series.tolist() for k, v in clus.groupby("cluster")}

    Co = C.loc[order, order]
    plt.figure(figsize=(9.5, 8.5))
    plt.imshow(Co.values, cmap="RdBu_r", vmin=-1, vmax=1)
    plt.xticks(range(len(order)), order, rotation=90, fontsize=6)
    plt.yticks(range(len(order)), order, fontsize=6)
    plt.colorbar(shrink=0.6, label="correlation of monthly changes")
    plt.title("Core panel, 1990+, clustered")
    plt.grid(False)
    fig("02_correlation_heatmap")

    plt.figure(figsize=(6.5, 9))
    dendrogram(Z, labels=list(C.columns), orientation="left", leaf_font_size=6,
               color_threshold=Z[-5, 2])
    plt.title("What moves together (average linkage on 1 - r)")
    plt.xlabel("distance")
    fig("03_dendrogram")
    return C


# ------------------------------------------------------- 6. factor structure
def section_pca():
    X = CH[CORE].loc["1998":].dropna(axis=1, thresh=200).dropna()
    if len(X) < 60:
        X = CH[CORE].loc["1998":].dropna(axis=1, thresh=150).ffill(limit=1).dropna()
    Xs = (X - X.mean()) / X.std()
    p = PCA().fit(Xs.values)
    ev = p.explained_variance_ratio_
    load = pd.DataFrame(p.components_[:4].T, index=X.columns,
                        columns=[f"PC{i+1}" for i in range(4)])
    save(load.reset_index().rename(columns={"index": "series"}), "06_pca_loadings")
    OUT["pca"] = {
        "n_months": int(len(X)), "n_series": int(X.shape[1]),
        "explained": [round(float(v), 4) for v in ev[:6]],
        "cum_top3": round(float(ev[:3].sum()), 4),
        "pc_top": {f"PC{i+1}": load[f"PC{i+1}"].abs().sort_values(ascending=False)
                   .head(6).index.tolist() for i in range(4)},
    }

    _, ax = plt.subplots(1, 2, figsize=(10, 4.2))
    k = min(10, len(ev))
    ax[0].bar(range(1, k + 1), ev[:k] * 100, color="#357")
    ax[0].plot(range(1, k + 1), np.cumsum(ev[:k]) * 100, "o-", color="#c44", ms=3)
    ax[0].set_xlabel("principal component")
    ax[0].set_ylabel("% of variance")
    ax[0].set_title(f"{X.shape[1]} series, {len(X)} months")
    top = load["PC1"].sort_values()
    ax[1].barh(range(len(top)), top.values,
               color=["#c44" if v < 0 else "#357" for v in top.values])
    ax[1].set_yticks(range(len(top)))
    ax[1].set_yticklabels(top.index, fontsize=5.5)
    ax[1].set_title("PC1 loadings")
    fig("04_pca")
    return load


# ------------------------------------------------------------ 7. lead / lag
def section_leadlag(max_lag=6, min_n=120):
    rows = []
    for a, b in itertools.permutations(CORE, 2):
        for L in range(1, max_lag + 1):
            d = pd.concat([CH[a].shift(L), CH[b]], axis=1).dropna()
            n = len(d)
            if n < min_n:
                continue
            r = d.iloc[:, 0].corr(d.iloc[:, 1])
            if not np.isfinite(r):
                continue
            t = r * np.sqrt(n - 2) / np.sqrt(max(1e-12, 1 - r * r))
            rows.append({"driver": a, "target": b, "lag_months": L, "n": n, "r": r,
                         "t_ols": t, "p_ols": 2 * sps.t.sf(abs(t), n - 2)})
    df = pd.DataFrame(rows)
    rej, adj = sc.fdr(df.p_ols)
    df["p_fdr"] = adj
    df["sig_fdr"] = rej
    df["abs_r"] = df.r.abs()
    df = df.sort_values("abs_r", ascending=False).reset_index(drop=True)
    save(df, "07_leadlag_all")

    eq = df[df.target == EQ].copy().reset_index(drop=True)
    hac = [sc.hac_corr(CH[row.driver].shift(row.lag_months), CH[EQ])
           for row in eq.head(60).itertuples()]
    eq["hac_t"] = np.nan
    eq["hac_p"] = np.nan
    eq.loc[: len(hac) - 1, "hac_t"] = [h[1] if h else np.nan for h in hac]
    eq.loc[: len(hac) - 1, "hac_p"] = [h[2] if h else np.nan for h in hac]
    save(eq, "08_leadlag_equity")

    OUT["leadlag"] = {
        "tests": int(len(df)), "sig_fdr": int(df.sig_fdr.sum()),
        "max_abs_r_any": round(float(df.abs_r.max()), 4),
        "top_any": df.head(25)[["driver", "target", "lag_months", "n", "r", "p_fdr"]]
                   .round(4).to_dict("records"),
        "equity_tests": int(len(eq)),
        "equity_sig_fdr": int(eq.sig_fdr.sum()),
        "equity_top": eq.head(20)[["driver", "lag_months", "n", "r", "t_ols",
                                   "hac_t", "hac_p", "p_fdr", "sig_fdr"]]
                      .round(4).to_dict("records"),
    }

    same = []
    for c in CORE:
        if c == EQ:
            continue
        h0 = sc.hac_corr(CH[c], CH[EQ])
        h1 = sc.hac_corr(CH[c].shift(1), CH[EQ])
        if h0 and h1:
            same.append({"series": c, "r_same_month": h0[0], "r_next_month": h1[0],
                         "hac_p_same": h0[2], "hac_p_next": h1[2],
                         "n": min(h0[3], h1[3])})
    sdf = save(pd.DataFrame(same).sort_values("r_same_month"), "09_same_vs_next")
    plt.figure(figsize=(8.5, 7))
    y = np.arange(len(sdf))
    plt.barh(y - 0.2, sdf.r_same_month, 0.4, label="same month", color="#357")
    plt.barh(y + 0.2, sdf.r_next_month, 0.4, label="predicting next month", color="#e8a33d")
    plt.yticks(y, sdf.series, fontsize=6)
    plt.axvline(0, color="k", lw=0.8)
    nf = 2 / np.sqrt(sdf.n.median())
    plt.axvspan(-nf, nf, color="grey", alpha=0.18, label="noise band (+/-2/sqrt(n))")
    plt.xlabel("correlation with equity monthly return")
    plt.title("Everything that moves markets does so in the same month")
    plt.legend(fontsize=7, loc="lower right")
    fig("05_same_vs_next_month")
    OUT["same_vs_next"] = sdf.round(4).to_dict("records")
    return df


# ---------------------------------------------------------- 8. granger battery
def section_granger():
    rows = []
    for a, b in itertools.permutations(CORE, 2):
        g = sc.granger(CH[a], CH[b], maxlag=3)
        if g:
            rows.append({"driver": a, "target": b, "F": g[0], "p": g[1],
                         "n": g[2], "maxlag": g[3]})
    df = pd.DataFrame(rows)
    rej, adj = sc.fdr(df.p)
    df["p_fdr"] = adj
    df["sig_fdr"] = rej
    df = df.sort_values("p").reset_index(drop=True)
    save(df, "10_granger")

    eq = df[df.target == EQ]
    out_eq = df[df.driver == EQ]
    OUT["granger"] = {
        "tests": int(len(df)), "sig_fdr": int(df.sig_fdr.sum()),
        "top": df.head(25)[["driver", "target", "F", "p", "p_fdr", "n"]].round(5).to_dict("records"),
        "into_equity_sig": int(eq.sig_fdr.sum()),
        "into_equity_top": eq.head(12)[["driver", "F", "p", "p_fdr", "n"]].round(5).to_dict("records"),
        "out_of_equity_sig": int(out_eq.sig_fdr.sum()),
        "out_of_equity_top": out_eq.head(12)[["target", "F", "p", "p_fdr", "n"]].round(5).to_dict("records"),
    }
    return df


# --------------------------------------------------------- 9. cointegration
def section_cointegration():
    pairs = [("US 10-year yield", "US 2-year yield"), ("Brent (long)", "WTI (long)"),
             ("US CPI", "US core CPI"), ("Gold", "US CPI"), (EQ, "US CPI"),
             (EQ, "US M2 money supply"), ("Gold", "USD broad index"),
             ("US 30-year mortgage rate", "US 10-year yield"),
             ("Bitcoin", EQ), ("Gold", "Bitcoin"), ("S&P PE10", "US 10-year yield")]
    rows = []
    for a, b in pairs:
        if a not in LV or b not in LV:
            continue
        d = pd.concat([LV[a], LV[b]], axis=1).dropna()
        if len(d) < 80:
            continue
        try:
            t, p, _ = coint(d.iloc[:, 0], d.iloc[:, 1])
        except Exception:
            continue
        beta = sm.OLS(d.iloc[:, 0], sm.add_constant(d.iloc[:, 1])).fit().params.iloc[1]
        rows.append({"x": a, "y": b, "n": len(d), "eg_t": t, "eg_p": p,
                     "hedge_beta": beta, "cointegrated_5pct": bool(p < 0.05)})
    df = save(pd.DataFrame(rows), "11_cointegration")
    OUT["cointegration"] = df.round(4).to_dict("records")
    return df


# ------------------------------------------------------------- 10. regimes
def section_regimes():
    specs = [(EQ, "US 10-year yield", "equities vs 10y yield change"),
             (EQ, "VIX", "equities vs VIX"),
             ("Bitcoin", EQ, "bitcoin vs equities"),
             ("Gold", "10y real yield (TIPS)", "gold vs real yield"),
             (EQ, "USD broad index", "equities vs dollar"),
             ("Gold", EQ, "gold vs equities")]
    rows = []
    plt.figure(figsize=(9, 5))
    for a, b, lab in specs:
        if a not in CH or b not in CH:
            continue
        d = pd.concat([CH[a], CH[b]], axis=1).dropna()
        if len(d) < 80:
            continue
        roll = d.iloc[:, 0].rolling(60).corr(d.iloc[:, 1])
        plt.plot(roll.index, roll.values, lw=1.2, label=lab)
        for dec in range(1970, 2030, 10):
            s = d.loc[str(dec):str(dec + 9)]
            if len(s) >= 24:
                rows.append({"pair": lab, "decade": f"{dec}s", "n": len(s),
                             "r": s.iloc[:, 0].corr(s.iloc[:, 1])})
    plt.axhline(0, color="k", lw=0.8)
    plt.ylabel("rolling 60-month correlation")
    plt.title("The sign itself is not stable: regimes, not constants")
    plt.legend(fontsize=7, ncol=2)
    fig("06_rolling_correlations")
    df = save(pd.DataFrame(rows), "12_regimes_by_decade")
    OUT["regimes"] = df.round(3).to_dict("records")

    piv = df.pivot_table(index="decade", columns="pair", values="r")
    OUT["regime_sign_flips"] = {
        c: bool((piv[c].dropna() > 0.1).any() and (piv[c].dropna() < -0.1).any())
        for c in piv.columns}
    return df


# --------------------------------------------------------- 11. event studies
def section_events():
    r = CH[EQ]
    shocks = ["VIX", "Geopolitical risk", "Geopolitical threats", "Geopolitical acts",
              "US economic policy uncertainty", "US equity market uncertainty",
              "St. Louis financial stress", "Chicago financial conditions",
              "Supply chain pressure", "US unemployment rate", "Initial jobless claims",
              "EPU Global"]
    rows = []
    for name in shocks:
        if name not in LV:
            continue
        s = LV[name]
        z = (s - s.rolling(60, min_periods=36).mean()) / s.rolling(60, min_periods=36).std()
        d = pd.concat([z.rename("z"), r.rename("m0"), r.shift(-1).rename("m1"),
                       r.shift(-1).rolling(3).sum().shift(-2).rename("m1_3"),
                       r.shift(-1).rolling(12).sum().shift(-11).rename("m1_12")],
                      axis=1).dropna()
        if len(d) < 80:
            continue
        hi = d[d.z > 1.5]
        if len(hi) < 8:
            continue
        for h in ["m0", "m1", "m1_3", "m1_12"]:
            m, lo, up = sc.block_bootstrap_mean(hi[h])
            p = sc.diff_in_means_p(hi[h], d[h])
            rows.append({"shock": name, "horizon": h, "n_spikes": len(hi),
                         "n_all": len(d), "mean_after_spike": m,
                         "ci_lo": lo, "ci_hi": up, "baseline": d[h].mean(),
                         "excess": m - d[h].mean(), "boot_p": p})
    df = pd.DataFrame(rows)
    rej, adj = sc.fdr(df.boot_p)
    df["p_fdr"] = adj
    df["sig_fdr"] = rej
    save(df, "13_event_study")
    OUT["events"] = df.round(4).to_dict("records")

    sub = df[df.horizon.isin(["m0", "m1"])]
    piv = sub.pivot_table(index="shock", columns="horizon", values="excess") * 100
    piv = piv.sort_values("m0")
    plt.figure(figsize=(8, 4.8))
    y = np.arange(len(piv))
    plt.barh(y - 0.2, piv["m0"], 0.4, label="same month", color="#357")
    plt.barh(y + 0.2, piv["m1"], 0.4, label="next month", color="#e8a33d")
    plt.yticks(y, piv.index, fontsize=7)
    plt.axvline(0, color="k", lw=0.8)
    plt.xlabel("excess equity return vs baseline, %")
    plt.title("Shock months (z>1.5): the hit lands immediately, nothing follows")
    plt.legend(fontsize=7)
    fig("07_event_study")
    return df


# --------------------------------------------- 12. out-of-sample walk-forward
def section_oos(min_train=180):
    r = CH[EQ]
    rows = []
    for c in [x for x in CORE if x != EQ]:
        d = pd.concat([CH[c].shift(1).rename("x"), r.rename("y")], axis=1).dropna()
        if len(d) < min_train + 60:
            continue
        X = d["x"].to_numpy(float)
        Y = d["y"].to_numpy(float)
        yhat, ytrue, bench = [], [], []
        for i in range(min_train, len(d)):
            b = np.polyfit(X[:i], Y[:i], 1)
            yhat.append(np.polyval(b, X[i]))
            bench.append(Y[:i].mean())
            ytrue.append(Y[i])
        yhat, ytrue, bench = map(np.asarray, (yhat, ytrue, bench))
        sse_m = float(((ytrue - yhat) ** 2).sum())
        sse_b = float(((ytrue - bench) ** 2).sum())
        rows.append({"predictor": c, "n_oos": len(ytrue),
                     "r2_oos": 1 - sse_m / sse_b,
                     "sign_accuracy": float((np.sign(yhat) == np.sign(ytrue)).mean()),
                     "in_sample_r": float(np.corrcoef(X, Y)[0, 1])})
    df = pd.DataFrame(rows).sort_values("r2_oos", ascending=False).reset_index(drop=True)
    save(df, "14_out_of_sample")
    OUT["oos"] = {
        "tested": int(len(df)),
        "positive_r2": int((df.r2_oos > 0).sum()),
        "best": df.head(10).round(4).to_dict("records"),
        "worst": df.tail(5).round(4).to_dict("records"),
        "median_r2": round(float(df.r2_oos.median()), 5),
        "median_sign_acc": round(float(df.sign_accuracy.median()), 4),
        "base_rate_up_months": round(float((CH[EQ].dropna() > 0).mean()), 4),
    }

    plt.figure(figsize=(7.5, 5))
    d2 = df.sort_values("r2_oos")
    plt.barh(range(len(d2)), d2.r2_oos * 100,
             color=["#357" if v > 0 else "#c44" for v in d2.r2_oos])
    plt.yticks(range(len(d2)), d2.predictor, fontsize=5.5)
    plt.axvline(0, color="k", lw=0.9)
    plt.xlabel("out-of-sample R2 vs the historical mean, %")
    plt.title("Walk-forward: almost nothing beats 'assume the average'")
    fig("08_out_of_sample_r2")
    return df


# --------------------------------------- 13. returns vs volatility predictability
def section_vol():
    r = CH[EQ].dropna()
    rows = []
    for name, s in [("return", r), ("abs return (volatility)", r.abs()),
                    ("squared return", r ** 2)]:
        lb = acorr_ljungbox(s, lags=[1, 3, 6, 12], return_df=True)
        for lag, row in lb.iterrows():
            rows.append({"series": name, "lag": int(lag),
                         "ljung_box_Q": row.lb_stat, "p": row.lb_pvalue,
                         "autocorr": s.autocorr(int(lag))})
    df = save(pd.DataFrame(rows), "15_return_vs_vol_predictability")
    OUT["volatility"] = df.round(5).to_dict("records")

    plt.figure(figsize=(7.5, 3.8))
    lags = list(range(1, 25))
    plt.bar([l - 0.2 for l in lags], [r.autocorr(l) for l in lags], 0.4,
            label="returns", color="#357")
    plt.bar([l + 0.2 for l in lags], [r.abs().autocorr(l) for l in lags], 0.4,
            label="|returns| (volatility)", color="#c44")
    ci = 1.96 / np.sqrt(len(r))
    plt.axhspan(-ci, ci, color="grey", alpha=0.2)
    plt.axhline(0, color="k", lw=0.8)
    plt.xlabel("lag, months")
    plt.ylabel("autocorrelation")
    plt.title("Direction is unpredictable; size is very predictable")
    plt.legend(fontsize=7)
    fig("09_return_vs_volatility_autocorr")

    OUT["tails"] = {
        "n": int(len(r)),
        "skew": round(float(sps.skew(r)), 3),
        "excess_kurtosis": round(float(sps.kurtosis(r)), 3),
        "jarque_bera_p": float(sps.jarque_bera(r).pvalue),
        "worst_month": round(float(r.min()), 4),
        "best_month": round(float(r.max()), 4),
        "sd": round(float(r.std()), 4),
        "n_beyond_3sd": int((r.abs() > 3 * r.std()).sum()),
        "n_expected_3sd_normal": round(float(len(r) * 0.0027), 2),
    }
    return df


# ----------------------------------------------------------- 14. link network
def section_network(cdf):
    d = cdf[(cdf.sig_fdr) & (cdf.abs_r >= 0.35) & (~cdf.near_duplicate)
            & (cdf.x.isin(CORE)) & (cdf.y.isin(CORE))]
    G = nx.Graph()
    for row in d.itertuples():
        G.add_edge(row.x, row.y, weight=abs(row.r), sign=np.sign(row.r))
    if not len(G):
        return
    plt.figure(figsize=(10, 8))
    pos = nx.spring_layout(G, seed=3, k=0.75, weight="weight")
    ec = ["#357" if G[a][b]["sign"] > 0 else "#c44" for a, b in G.edges()]
    ew = [G[a][b]["weight"] * 3.2 for a, b in G.edges()]
    nx.draw_networkx_edges(G, pos, edge_color=ec, width=ew, alpha=0.65)
    nx.draw_networkx_nodes(G, pos, node_size=[80 + 45 * G.degree(n) for n in G],
                           node_color="#eee", edgecolors="#555", linewidths=0.6)
    nx.draw_networkx_labels(G, pos, font_size=6.5)
    plt.title("Same-month links with |r| >= 0.35 (blue = same direction, red = opposite)")
    plt.axis("off")
    fig("10_network")
    deg = sorted(G.degree, key=lambda t: -t[1])
    OUT["network"] = {"nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
                      "most_connected": [{"series": n, "links": k} for n, k in deg[:10]]}


def main():
    print("1  coverage"); section_coverage()
    print("2  stationarity"); section_stationarity()
    print("3  levels vs changes"); section_spurious()
    print("4  contemporaneous"); cdf = section_contemporaneous()
    print("5  clustering"); section_clusters()
    print("6  pca"); section_pca()
    print("7  lead/lag"); section_leadlag()
    print("8  granger"); section_granger()
    print("9  cointegration"); section_cointegration()
    print("10 regimes"); section_regimes()
    print("11 event studies"); section_events()
    print("12 out-of-sample"); section_oos()
    print("13 vol vs return"); section_vol()
    print("14 network"); section_network(cdf)
    (HERE / "summary.json").write_text(json.dumps(OUT, indent=1, default=str))
    print(f"\nwrote {len(list(TAB.glob('*.csv')))} tables, "
          f"{len(list(CHT.glob('*.png')))} charts, summary.json")


if __name__ == "__main__":
    main()
