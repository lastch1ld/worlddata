"""Shared helpers: HTTP with a real user agent, a disk cache, and dataset writing.

Every collector writes the SAME shape so the datasets stay importable:

    data/<name>.csv    - tidy long format, one observation per row
    data/<name>.json   - the same rows, for the browser
    data/<name>.meta.json - source URL, licence, row count, retrieval date

Tidy long format means columns [date, series, value, ...] rather than one column per
series. It is less pretty to read but it survives new series being added without changing
the schema, which is the whole point of a dataset other people import.
"""
import hashlib
import io
import json
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / "cache"
JSON_ROW_CAP = 60_000   # above this the browser JSON is thinned; see write()
UA = {"User-Agent": "worlddata-collector/0.1 (+https://github.com/lastch1ld/worlddata)"}


def fetch(url, binary=True, timeout=120, force=False):
    """GET with a disk cache, so re-running a build does not re-hammer the source."""
    CACHE.mkdir(exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    f = CACHE / f"{key}.bin"
    if f.exists() and not force:
        return f.read_bytes() if binary else f.read_text(encoding="utf-8", errors="replace")
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    f.write_bytes(r.content)
    return r.content if binary else r.text


def read_excel(url, **kw):
    return pd.read_excel(io.BytesIO(fetch(url)), **kw)


def write(name, df, source, licence, note="", value_col="value"):
    """Write one dataset in all three forms, and validate it before it lands.

    The checks here are the difference between a dataset and a pile of numbers: no empty
    frames, no all-null values, no duplicate keys, dates that actually parse.
    """
    DATA.mkdir(exist_ok=True)
    assert len(df), f"{name}: empty dataset"
    assert value_col in df.columns, f"{name}: no '{value_col}' column"
    assert df[value_col].notna().any(), f"{name}: every value is null"
    if "date" in df.columns:
        bad = pd.to_datetime(df["date"], errors="coerce").isna().sum()
        assert bad == 0, f"{name}: {bad} unparseable dates"
    df = df.reset_index(drop=True)

    df.to_csv(DATA / f"{name}.csv", index=False)

    # The CSV is canonical and complete. The JSON exists for the browser, and above a few
    # tens of thousands of rows it stops being useful for that: market_drivers as raw JSON
    # is 45 MB, which doubles the repo and hangs the page before it draws anything. Above
    # JSON_ROW_CAP the JSON is thinned to month-end per series - enough to chart, useless
    # for analysis - and the metadata says so, so nobody mistakes it for the full data.
    json_df, thinned = df, False
    if len(df) > JSON_ROW_CAP and "date" in df.columns and "series" in df.columns:
        d = df.copy()
        d["_m"] = pd.to_datetime(d["date"], errors="coerce").dt.to_period("M")
        json_df = (d.dropna(subset=["_m"]).sort_values("date")
                   .groupby(["series", "_m"], as_index=False).last().drop(columns="_m"))
        thinned = True
    (DATA / f"{name}.json").write_text(
        json_df.to_json(orient="records", date_format="iso"), encoding="utf-8")

    meta = {"name": name, "rows": len(df), "columns": list(df.columns),
            "source": source, "licence": licence, "note": note,
            "json_rows": len(json_df), "json_thinned": thinned,
            "retrieved": date.today().isoformat()}
    if thinned:
        meta["json_note"] = ("JSON is thinned to month-end per series for the browser. "
                             "Use the CSV for anything real - it is complete.")
    if "date" in df.columns:
        meta["span"] = [str(df["date"].min()), str(df["date"].max())]
    if "series" in df.columns:
        meta["series"] = sorted(df["series"].astype(str).unique().tolist())
    (DATA / f"{name}.meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"  {name:<22}{len(df):>8,} rows  {len(meta.get('series', [])):>4} series")
    return meta
