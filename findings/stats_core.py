"""Statistical helpers shared by the analysis.

Three things are done deliberately and are worth knowing about:

* Every t-statistic on a time series uses Newey-West (HAC) standard errors.
  Monthly macro/market changes are serially correlated and heteroskedastic, and
  a plain OLS t-stat over-states significance, sometimes by a factor of two.
* Every family of tests is corrected with Benjamini-Hochberg FDR. Scanning
  ~9,000 pairs at p<0.05 produces ~450 false positives; without correction the
  "findings" would be mostly noise.
* Confidence intervals on event-study means come from a stationary block
  bootstrap, which preserves volatility clustering that an iid bootstrap breaks.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

HAC_LAGS = 4  # ~ 4 monthly lags, standard for monthly data


def hac_corr(x, y, lags=HAC_LAGS):
    """Correlation of two aligned series plus a HAC-robust t-stat and p-value.

    Returns (r, t, p, n) or None if the overlap is too short.
    """
    d = pd.concat([x, y], axis=1).dropna()
    n = len(d)
    if n < 30:
        return None
    a = d.iloc[:, 0].to_numpy(float)
    b = d.iloc[:, 1].to_numpy(float)
    if a.std() == 0 or b.std() == 0:
        return None
    a = (a - a.mean()) / a.std()
    b = (b - b.mean()) / b.std()
    m = sm.OLS(b, sm.add_constant(a)).fit(cov_type="HAC",
                                          cov_kwds={"maxlags": lags})
    r = float(np.corrcoef(a, b)[0, 1])
    return r, float(m.tvalues[1]), float(m.pvalues[1]), n


def fdr(pvals, alpha=0.05):
    """Benjamini-Hochberg. Returns (reject_flags, adjusted_pvals)."""
    p = np.asarray(pvals, dtype=float)
    ok = np.isfinite(p)
    rej = np.zeros(len(p), bool)
    adj = np.ones(len(p))
    if ok.sum():
        r, a, _, _ = multipletests(p[ok], alpha=alpha, method="fdr_bh")
        rej[ok] = r
        adj[ok] = a
    return rej, adj


def granger(x, y, maxlag=3, lags=HAC_LAGS):
    """Does x help predict y beyond y's own past? HAC-robust Wald test.

    Written out rather than using statsmodels' grangercausalitytests so the
    covariance estimator is robust and the lag structure is explicit.
    Returns (F, p, n, maxlag) or None.
    """
    d = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(d) < 60:
        return None
    cols = {}
    for L in range(1, maxlag + 1):
        cols[f"y{L}"] = d["y"].shift(L)
        cols[f"x{L}"] = d["x"].shift(L)
    X = pd.DataFrame(cols, index=d.index).dropna()
    yv = d["y"].reindex(X.index)
    if len(X) < 50:
        return None
    m = sm.OLS(yv.to_numpy(float), sm.add_constant(X.to_numpy(float))).fit(
        cov_type="HAC", cov_kwds={"maxlags": lags})
    names = ["const"] + list(X.columns)
    R = np.zeros((maxlag, len(names)))
    for i, L in enumerate(range(1, maxlag + 1)):
        R[i, names.index(f"x{L}")] = 1.0
    w = m.wald_test(R, scalar=True)
    return float(w.statistic), float(w.pvalue), int(len(X)), maxlag


def block_bootstrap_mean(v, n_boot=5000, block=6, seed=0):
    """Mean and 95% CI of a series via a circular block bootstrap."""
    v = np.asarray(pd.Series(v).dropna(), dtype=float)
    n = len(v)
    if n < 5:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    means = v[idx.reshape(n_boot, -1)[:, :n]].mean(axis=1)
    return float(v.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def diff_in_means_p(sample, population, n_boot=5000, block=6, seed=0):
    """Two-sided bootstrap p-value that sample mean differs from population mean."""
    s = np.asarray(pd.Series(sample).dropna(), dtype=float)
    p_all = np.asarray(pd.Series(population).dropna(), dtype=float)
    if len(s) < 5 or len(p_all) < 30:
        return np.nan
    obs = s.mean() - p_all.mean()
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(len(s) / block))
    starts = rng.integers(0, len(p_all), size=(n_boot, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % len(p_all)
    draws = p_all[idx.reshape(n_boot, -1)[:, :len(s)]].mean(axis=1) - p_all.mean()
    return float((np.abs(draws) >= abs(obs)).mean())
