"""Build every dataset, then a manifest the web UI reads.

    python build.py            # build everything
    python build.py --check    # validate what is already in data/, fetch nothing
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def build():
    from collectors import commodities, companies, datahub, events, rates, registry
    print("building datasets\n")
    rates.collect()
    commodities.collect()
    companies.collect()
    events.collect()          # policy changes derive from rates, so this runs last
    datahub.collect()
    registry.collect()
    manifest()


def manifest():
    """One index file so the UI can discover datasets without hardcoding names."""
    entries = []
    for m in sorted(DATA.glob("*.meta.json")):
        entries.append(json.loads(m.read_text(encoding="utf-8")))
    (DATA / "manifest.json").write_text(
        json.dumps({"datasets": entries}, indent=1), encoding="utf-8")
    print(f"\nmanifest: {len(entries)} datasets, "
          f"{sum(e['rows'] for e in entries):,} rows total")
    return entries


def check():
    """Validate the committed datasets without touching the network.

    Runs in CI and before a commit: catches a dataset that was truncated, lost its dates,
    or drifted schema, which is the failure mode that quietly breaks everyone importing it.
    """
    import pandas as pd
    assert DATA.exists(), "no data/ directory - run `python build.py` first"
    metas = list(DATA.glob("*.meta.json"))
    assert metas, "no datasets found"
    for m in sorted(metas):
        meta = json.loads(m.read_text(encoding="utf-8"))
        name = meta["name"]
        csv, js = DATA / f"{name}.csv", DATA / f"{name}.json"
        assert csv.exists() and js.exists(), f"{name}: missing csv or json"
        df = pd.read_csv(csv)
        assert len(df) == meta["rows"], (
            f"{name}: csv has {len(df)} rows, meta claims {meta['rows']}")
        assert list(df.columns) == meta["columns"], f"{name}: column drift"
        assert df["value"].notna().any(), f"{name}: all values null"
        if "date" in df.columns:
            bad = pd.to_datetime(df["date"], errors="coerce").isna().sum()
            assert bad == 0, f"{name}: {bad} unparseable dates"
        assert meta.get("licence"), f"{name}: no licence recorded"
        assert meta.get("source"), f"{name}: no source recorded"
        print(f"  ok  {name:<22}{len(df):>8,} rows")
    print(f"\n{len(metas)} datasets validated")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    p.add_argument("--verify-links", action="store_true",
                   help="GET every registry URL; a dead link fails here, not for a user")
    a = p.parse_args()
    if a.verify_links:
        from collectors import registry
        registry.verify()
    elif a.check:
        check()
    else:
        build()
