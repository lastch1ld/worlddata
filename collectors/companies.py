"""Largest companies by market capitalisation, revenue and profit.

HONEST LIMIT, READ THIS FIRST
The ask was top 100 per year on three metrics. Free sources do not carry that:

  Wikipedia "public corporations by market capitalization"  top 10 per QUARTER, ~2010+
  Wikipedia "Forbes Global 2000"                            top 10 per YEAR, sales/profit/assets
  Wikipedia "largest companies by revenue"                  top 50, CURRENT YEAR only

So this collector emits what actually exists and labels the depth on every row, rather than
padding to 100 with invented entries. Getting to a real top 100 per year needs one of:

  - Fortune 500 / Forbes Global 2000 full lists (their sites; check terms before scraping)
  - SEC bulk filings via EDGAR (free, authoritative, but you assemble market cap yourself
    from shares outstanding x price, per company per year - a much bigger job)
  - A paid vendor (Compustat, Refinitiv) - the usual answer for point-in-time constituents

Also note SURVIVORSHIP: these lists are as published at the time, which is what you want.
A "top 100 by market cap today, backfilled" list is a different and much less useful thing.

Licence: Wikipedia content is CC BY-SA 4.0. Attribute and share alike.
"""
import io
import re

import pandas as pd

from .common import fetch, write

MCAP_URL = "https://en.wikipedia.org/wiki/List_of_public_corporations_by_market_capitalization"
FORBES_URL = "https://en.wikipedia.org/wiki/Forbes_Global_2000"
REVENUE_URL = "https://en.wikipedia.org/wiki/List_of_largest_companies_by_revenue"


def _num(x):
    """Wikipedia numbers carry footnote markers, commas and currency symbols."""
    s = re.sub(r"\[.*?\]", "", str(x))
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _clean_name(x):
    return re.sub(r"\[.*?\]", "", str(x)).strip()


def _year_before(html, table_index):
    """Find the nearest preceding 4-digit year heading for the Nth wikitable."""
    parts = html.split('class="wikitable')
    if table_index + 1 >= len(parts):
        return None
    years = re.findall(r"id=\"[^\"]*?(\d{4})", parts[table_index])
    if not years:
        years = re.findall(r">(\d{4})<", parts[table_index])
    return int(years[-1]) if years else None


def collect_forbes():
    """Forbes Global 2000 top 10 per year: sales, profits, assets - three metrics at once."""
    html = fetch(FORBES_URL, binary=False)
    tables = pd.read_html(io.StringIO(html))
    rows = []
    idx = 0
    for t in tables:
        if t.shape[0] != 10 or "Company" not in [str(c) for c in t.columns]:
            continue
        idx += 1
        year = _year_before(html, idx)
        cols = {str(c).lower(): c for c in t.columns}
        sales = next((v for k, v in cols.items() if "sales" in k), None)
        profit = next((v for k, v in cols.items() if "profit" in k), None)
        assets = next((v for k, v in cols.items() if "asset" in k), None)
        mval = next((v for k, v in cols.items() if "market value" in k), None)
        for _, r in t.iterrows():
            base = dict(year=year, rank=_num(r.get("Rank")), company=_clean_name(r["Company"]),
                        list_depth=10, source_list="Forbes Global 2000")
            for metric, col in (("revenue", sales), ("profit", profit),
                                ("assets", assets), ("market_cap", mval)):
                if col is not None and _num(r.get(col)) is not None:
                    rows.append({**base, "metric": metric, "value": _num(r.get(col)),
                                 "unit": "USD billions"})
    df = pd.DataFrame(rows).dropna(subset=["year"])
    df["year"] = df["year"].astype(int)
    return df


def collect_revenue_current():
    """Top 50 by revenue for the current list, with profit alongside."""
    t = pd.read_html(io.StringIO(fetch(REVENUE_URL, binary=False)))[0]
    t.columns = [" ".join(dict.fromkeys(map(str, c))) if isinstance(c, tuple) else str(c)
                 for c in t.columns]
    name = next(c for c in t.columns if "Name" in c)
    rev = next(c for c in t.columns if "Revenue" in c)
    prof = next((c for c in t.columns if "Profit" in c), None)
    rank = next(c for c in t.columns if "Rank" in c)
    rows = []
    for _, r in t.iterrows():
        base = dict(year=None, rank=_num(r[rank]), company=_clean_name(r[name]),
                    list_depth=len(t), source_list="Wikipedia largest by revenue")
        rows.append({**base, "metric": "revenue", "value": _num(r[rev]),
                     "unit": "USD billions"})
        if prof:
            rows.append({**base, "metric": "profit", "value": _num(r[prof]),
                         "unit": "USD billions"})
    return pd.DataFrame(rows).dropna(subset=["value"])


def collect():
    forbes = collect_forbes()
    current = collect_revenue_current()
    # the current list has no year on the page; stamp it with the newest Forbes year
    if len(forbes):
        current["year"] = int(forbes["year"].max())
    out = pd.concat([forbes, current], ignore_index=True)
    out = out.dropna(subset=["value", "company"])
    # Series name carries the list depth. Without it a top-10 year and a top-50 year land in
    # the same series and get summed together downstream, which makes revenue appear to jump
    # 6x in one year purely because the list got deeper. Different depth = different series.
    out["series"] = out["metric"] + "_top" + out["list_depth"].astype(int).astype(str)
    out["date"] = out["year"].astype(int).astype(str) + "-12-31"
    out = out[["date", "year", "series", "metric", "company", "rank", "value", "unit",
               "list_depth", "source_list"]].sort_values(["metric", "year", "rank"])
    assert out["metric"].nunique() >= 3, f"expected 3+ metrics, got {out['metric'].unique()}"
    return write("companies_top", out,
                 source=f"{FORBES_URL} ; {REVENUE_URL}",
                 licence="Wikipedia CC BY-SA 4.0",
                 note=("Top 10 per year (Forbes Global 2000) plus current top 50 by revenue. "
                       "list_depth says how deep each list goes - free sources do NOT provide "
                       "top 100 per year. See the module docstring for how to get that."))


if __name__ == "__main__":
    collect()
