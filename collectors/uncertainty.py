"""Uncertainty indices: economic policy, trade policy, and the IMF world index.

GPR (georisk.py) measures how much newspapers talk about war. This measures how much they
talk about not knowing what governments will do, which is a different and often earlier
signal - firms delay hiring and capex on uncertainty before any shock actually lands.

Three families, one collector because they share a publisher and a file shape:

  EPU   Baker, Bloom & Davis. Monthly, per country, from newspaper text. Also a CATEGORICAL
        breakdown for the US (monetary, fiscal, trade, healthcare, regulation, ...), which
        is the useful part: "uncertainty" as one number hides whether it is a tax fight or
        a trade war.
  TPU   Caldara et al. Trade policy uncertainty specifically, monthly to 1960 and daily.
        Separated out because trade shocks hit FX and commodities through different
        plumbing than domestic policy fights.
  WUI   Ahir, Bloom & Furceri (IMF). Quarterly, ~140 countries, from Economist Intelligence
        Unit country reports rather than newspapers - so it covers places with no usable
        newspaper archive, which is where EPU stops.

WHY THE COUNTRY LIST LOOKS ODD: the EPU site publishes one file per country, but Germany,
France and Italy have no standalone file - they live inside the Europe workbook as columns.
So the country loop skips them and the Europe file supplies them. Probed, not assumed:
requesting Germany_Policy_Uncertainty_Data.xlsx returns 404.

Licence: free for research with attribution. Baker, Bloom & Davis (2016), "Measuring
Economic Policy Uncertainty", QJE; Caldara, Iacoviello, Molligo, Prestipino & Raffo (2020),
"The Economic Effects of Trade Policy Uncertainty", JME; Ahir, Bloom & Furceri (2022),
"The World Uncertainty Index", NBER WP.
"""
import io
import re
import warnings
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from .common import fetch, write

BASE = "https://www.policyuncertainty.com/media"
TPU_URL = "https://www.matteoiacoviello.com/tpu_files/tpu_web_latest.xlsx"
CITE = ("Baker, Bloom & Davis (2016) QJE; Caldara et al. (2020) JME; "
        "Ahir, Bloom & Furceri (2022) NBER WP")

# One file per country. Germany, France and Italy are deliberately absent - they have no
# standalone file (404) and arrive via the Europe workbook instead.
COUNTRIES = ["US", "UK", "China", "Japan", "Spain", "Canada", "Australia", "Brazil",
             "India", "Korea", "Russia", "Mexico", "Netherlands", "Sweden", "Ireland",
             "Chile", "Colombia", "Singapore"]


MIN_OBS = 24        # fewer than two years of points is a note column, not a series


def _dates_from(d):
    """Find the time axis. These workbooks use three different conventions.

    Year+Month columns is the documented one. But Korea and Ireland ship a single `Date`
    column, and the Netherlands and Colombia leave it unnamed in column 0 - so falling back
    to "whatever parses as dates" is what gets those six countries in instead of dropped.
    """
    cols = {str(c).strip().lower(): c for c in d.columns}
    ycol, mcol = cols.get("year"), cols.get("month")
    if ycol is not None:
        y = pd.to_numeric(d[ycol], errors="coerce")
        keep = y.notna() & y.between(1850, 2100)
        m = pd.to_numeric(d[mcol], errors="coerce") if mcol else None
        if mcol:
            keep &= m.notna() & m.between(1, 12)
        if keep.sum() >= MIN_OBS:
            date = pd.to_datetime(dict(year=y[keep].astype(int),
                                       month=m[keep].astype(int) if mcol else 1, day=1),
                                  errors="coerce")
            return date, keep, {ycol, mcol}, 2
    for c in list(d.columns)[:2]:
        parsed = _as_dates(d[c])
        if parsed is None:
            continue
        keep = parsed.notna()
        # A real time axis moves. Without this, an integer column parses "successfully" as
        # nanoseconds since epoch and every row lands on 1970-01-01 - which is what Spain,
        # Chile and Colombia silently did before this check existed.
        if keep.sum() >= MIN_OBS and parsed[keep].dt.to_period("M").nunique() >= 12:
            named = not str(c).lower().startswith("unnamed")
            return parsed[keep], keep, {c}, (1 if named else 0)
    return None, None, set(), -1


def _as_dates(s):
    """Parse a column as dates, refusing the interpretations that are quietly wrong.

    Strings and real datetimes are parsed normally. A NUMERIC column is only accepted as an
    Excel serial date (days since 1899-12-30) and only when the values sit in a sane range,
    because pandas will otherwise read plain integers as epoch nanoseconds without
    complaining and put the whole series in 1970.
    """
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    if pd.api.types.is_numeric_dtype(s):
        v = pd.to_numeric(s, errors="coerce")
        if v.between(20000, 60000).mean() < 0.9:      # not Excel serials (1954-2064)
            return None
        return pd.to_datetime(v, unit="D", origin="1899-12-30", errors="coerce")
    p = _period_strings(s)                            # "1993m1" / "1996q1"
    if p is not None:
        return p
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")               # mixed formats are expected here
        return pd.to_datetime(s.astype(str), errors="coerce")


def _period_strings(s):
    """Parse the 'YYYYmM' and 'YYYYqQ' conventions these authors use (Chile, WUI).

    dateutil reads "1993m1" as nothing and "1996q1" as nothing, so without this the whole
    column falls through to NaT and the file looks unparseable.
    """
    t = s.astype(str).str.strip().str.lower()
    for pat, mult in ((r"^(\d{4})m(\d{1,2})$", 1), (r"^(\d{4})q([1-4])$", 3)):
        g = t.str.extract(pat)
        ok = g[0].notna()
        if ok.mean() < 0.5:
            continue
        out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
        month = (g.loc[ok, 1].astype(int) - 1) * mult + 1
        out[ok] = pd.to_datetime(dict(year=g.loc[ok, 0].astype(int), month=month, day=1),
                                 errors="coerce")
        return out
    return None


def _tidy(d, scope, prefix=""):
    """Wide frame -> tidy long. Drops note rows, note columns and unparseable dates.

    The workbooks end with free-text notes in the date column ("Note: index is..."), which
    is why the axis is coerced and NaNs dropped rather than trusted.
    """
    date, keep, used, quality = _dates_from(d)
    if date is None:
        return None, -1
    rows = []
    for c in d.columns:
        if c in used:
            continue
        # A purely numeric column NAME means the header row landed on data - the "series"
        # would be a melted month or year column. The US file produced exactly that: a
        # series named "8" whose values ran 1-12.
        if re.fullmatch(r"[\d.\s]+", str(c).strip()):
            return None, -1
        v = pd.to_numeric(d.loc[keep, c], errors="coerce")
        if v.notna().sum() < MIN_OBS:
            continue
        # These are all normalised indices (typically 0-1000). A column in the 1e12 range is
        # a timestamp that got melted in as a value, not a series.
        if v.abs().max() > 1e6:
            continue
        label = re.sub(r"[_\s]+", " ", str(c)).strip()
        label = re.sub(r"^\d+\.\s*", "", label)      # "9. Trade policy" -> "Trade policy"
        if label.lower().startswith("unnamed"):
            label = "index"
        rows.append(pd.DataFrame({"date": date, "series": f"{prefix}{label}",
                                  "scope": scope, "value": v, "unit": "index"}))
    if not rows:
        return None, -1
    out = pd.concat(rows, ignore_index=True)
    out = out[out["value"].notna() & out["date"].notna()]
    return (out, quality) if len(out) else (None, -1)


def _best_sheet(raw, scope, prefix):
    """Try every sheet, and headers on rows 0-3, keeping the best-QUALITY parse.

    Spain and Chile put the citation on row 1 and the real header below it, so a plain
    read_excel sees one column named after a journal article. Rather than hard-code a
    skiprows per country - which breaks the next time they re-export - this just tries.

    Ranking on row count alone does not work: pushing the header further down turns the
    Year and Month columns into data and yields MORE rows than the correct parse. So a
    Year/Month axis outranks a named date column, which outranks an unnamed one, and row
    count only breaks ties within a quality level.
    """
    best, best_key = None, None
    xl = pd.ExcelFile(io.BytesIO(raw))
    for sheet in xl.sheet_names:
        for header in range(4):
            try:
                d = xl.parse(sheet, header=header)
            except Exception:
                continue
            if d.empty or len(d.columns) < 2:
                continue
            t, q = _tidy(d, scope, prefix)
            if t is None:
                continue
            # Tiebreak on how many series came out with a REAL name. Chile's header row 0 is
            # a citation sentence, which counts as "named" and ties with the correct parse on
            # both quality and row count - but it yields two anonymous "index" series where
            # header row 2 yields EPU* and EPUC**.
            named = sum(not s.endswith(": index") for s in t["series"].unique())
            key = (q, named, len(t))
            if best_key is None or key > best_key:
                best, best_key = t, key
    return best


def _country(name):
    try:
        raw = fetch(f"{BASE}/{name}_Policy_Uncertainty_Data.xlsx")
    except Exception as e:
        return name, None, type(e).__name__
    t = _best_sheet(raw, scope=name, prefix=f"{name} EPU: ")
    return name, t, None if t is not None else "no usable columns"


def collect_epu(workers=6):
    frames, dropped = [], []

    g, _ = _tidy(pd.read_excel(io.BytesIO(fetch(f"{BASE}/Global_Policy_Uncertainty_Data.xlsx"))),
                 scope="global", prefix="Global EPU: ")
    if g is not None:
        frames.append(g)

    eu = pd.read_excel(io.BytesIO(fetch(f"{BASE}/Europe_Policy_Uncertainty_Data.xlsx")),
                       sheet_name="European News-Based Index")
    e, _ = _tidy(eu, scope="europe", prefix="Europe EPU: ")
    if e is not None:
        frames.append(e)

    cat = pd.read_excel(io.BytesIO(fetch(f"{BASE}/Categorical_EPU_Data.xlsx")),
                        sheet_name="Indices")
    c, _ = _tidy(cat, scope="US categorical", prefix="US EPU by category: ")
    if c is not None:
        frames.append(c)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for name, t, why in ex.map(_country, COUNTRIES):
            (frames.append(t) if t is not None else dropped.append((name, why)))
    for name, why in dropped:
        print(f"  ! dropped EPU {name}: {why}")

    assert len(frames) >= 15, f"only {len(frames)} EPU sources usable - site may have changed"
    out = pd.concat(frames, ignore_index=True).sort_values(["series", "date"])
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return write("uncertainty_epu", out,
                 source=f"{BASE}/ (one workbook per country)",
                 licence=f"Free for research with attribution. {CITE}",
                 note=("Economic policy uncertainty from newspaper text, monthly. Includes "
                       "the global index, the European workbook (which is where Germany, "
                       "France and Italy live - they have no standalone file), 18 country "
                       "files, and the US categorical breakdown (monetary, fiscal, trade, "
                       "regulation and so on), which is the part that says WHAT the "
                       "uncertainty is about."))


def _quarter_to_date(s):
    """Parse '1996q1' / '1996Q1' / 1996 into a period start date."""
    t = s.astype(str).str.strip().str.lower()
    q = t.str.extract(r"^(\d{4})q([1-4])$")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    ok = q[0].notna()
    if ok.any():
        out[ok] = pd.to_datetime(dict(year=q.loc[ok, 0].astype(int),
                                      month=(q.loc[ok, 1].astype(int) - 1) * 3 + 1, day=1))
    plain = ~ok & t.str.fullmatch(r"\d{4}(\.0)?")
    if plain.any():
        out[plain] = pd.to_datetime(dict(year=t[plain].str.slice(0, 4).astype(int),
                                         month=1, day=1))
    return out


# The WUI is republished at a dated path each year, and the copy mirrored on
# policyuncertainty.com is FIVE YEARS STALE - it ends 2019q3 while the live file runs to
# 2024q4. Both parse identically and nothing in the stale one says it is old, so the only
# defence is to fetch every candidate and keep whichever reaches furthest.
WUI_URLS = [
    "https://worlduncertaintyindex.com/wp-content/uploads/2025/01/WUI_Data.xlsx",
    "https://worlduncertaintyindex.com/wp-content/uploads/2024/01/WUI_Data.xlsx",
    "https://www.policyuncertainty.com/media/WUI_Data.xlsx",
]


def _newest_wui():
    """Return (url, ExcelFile) for whichever candidate has the latest last observation."""
    best = None
    for url in WUI_URLS:
        try:
            xl = pd.ExcelFile(io.BytesIO(fetch(url)))
            sheet = "T1" if "T1" in xl.sheet_names else xl.sheet_names[0]
            last = _quarter_to_date(xl.parse(sheet).iloc[:, 0]).max()
        except Exception as e:
            print(f"  ! WUI candidate failed ({type(e).__name__}): {url}")
            continue
        if pd.notna(last) and (best is None or last > best[0]):
            best = (last, url, xl)
    assert best, "no WUI candidate resolved"
    print(f"  WUI source: {best[1].split('/')[-3]}/{best[1].split('/')[-2]} "
          f"(to {best[0].date()})")
    return best[1], best[2]


def collect_wui():
    url, xl = _newest_wui()
    frames = []

    if "T1" in xl.sheet_names:                     # aggregates: global, by income, by region
        d = xl.parse("T1")
        first = d.columns[0]
        date = _quarter_to_date(d[first])
        for c in d.columns[1:]:
            v = pd.to_numeric(d[c], errors="coerce")
            if v.notna().sum() < 8:
                continue
            frames.append(pd.DataFrame({"date": date, "series": f"WUI {c}",
                                        "scope": "aggregate", "value": v, "unit": "index"}))

    if "T2" in xl.sheet_names:                     # country panel, wide by ISO3
        d = xl.parse("T2")
        first = d.columns[0]
        date = _quarter_to_date(d[first])
        for c in d.columns[1:]:
            iso = str(c).strip()
            if not re.fullmatch(r"[A-Z]{3}", iso):
                continue
            v = pd.to_numeric(d[c], errors="coerce")
            if v.notna().sum() < 8:
                continue
            frames.append(pd.DataFrame({"date": date, "series": f"WUI {iso}",
                                        "scope": iso, "value": v, "unit": "index"}))

    out = pd.concat(frames, ignore_index=True)
    out = out[out["value"].notna() & out["date"].notna()].sort_values(["series", "date"])
    n_country = (out["scope"] != "aggregate").sum()
    assert out["scope"].nunique() >= 50, f"only {out['scope'].nunique()} WUI scopes found"
    assert n_country > 0, "WUI country panel empty"
    assert out["date"].max() >= pd.Timestamp("2023-01-01"), (
        f"WUI ends {out['date'].max().date()} - fell back to the stale mirror")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return write("uncertainty_world", out,
                 source=url,
                 licence=f"Free for research with attribution. {CITE}",
                 note=("IMF World Uncertainty Index, quarterly. Built from Economist "
                       "Intelligence Unit country reports rather than newspapers, so it "
                       "reaches countries with no usable press archive - which is exactly "
                       "where EPU stops. Dates are quarter starts. The copy mirrored on "
                       "policyuncertainty.com ends in 2019 - this is fetched from the "
                       "newest release instead, see WUI_URLS."))


def collect_tpu():
    xl = pd.ExcelFile(io.BytesIO(fetch(TPU_URL)))
    frames = []
    for sheet, freq in [("TPU_MONTHLY", "monthly"), ("TPU_DAILY", "daily")]:
        if sheet not in xl.sheet_names:
            continue
        d = xl.parse(sheet)
        dcol = next((c for c in d.columns if str(c).strip().upper() == "DATE"), d.columns[0])
        date = pd.to_datetime(d[dcol], errors="coerce")
        for c in d.columns:
            if c == dcol:
                continue
            v = pd.to_numeric(d[c], errors="coerce")
            if v.notna().sum() < 50:
                continue
            frames.append(pd.DataFrame({"date": date, "series": f"{c} ({freq})",
                                        "scope": "US", "value": v,
                                        "unit": "index" if "TPU" in str(c) else "count"}))
    out = pd.concat(frames, ignore_index=True)
    out = out[out["value"].notna() & out["date"].notna()].sort_values(["series", "date"])
    assert out["date"].min().year <= 1970, f"TPU should reach 1960, starts {out['date'].min()}"
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return write("trade_policy_uncertainty", out,
                 source=TPU_URL,
                 licence=f"Free for research with attribution. {CITE}",
                 note=("Trade policy uncertainty, monthly back to 1960 and daily. Kept "
                       "apart from general EPU because trade shocks reach FX and "
                       "commodities through different plumbing than domestic policy "
                       "fights. TPU_RAW is the article count, TPU the scaled index."))


def collect():
    collect_epu()
    collect_wui()
    collect_tpu()


if __name__ == "__main__":
    collect()
