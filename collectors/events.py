"""Political events and policy changes.

Two different problems, handled differently:

POLICY CHANGES are DERIVED, not scraped. A central bank policy change is exactly a change
in its policy rate, and the BIS series dates those precisely. Deriving them means every
hike and cut for 49 countries back to 1946 comes out automatically, with the size of the
move, and it stays correct when BIS updates. Scraping press releases would be less complete
and would go stale.

Severity is assigned by size of move, which is a rule anyone can check:
    >= 75bp  major      (an emergency-sized move)
    >= 25bp  standard
    <  25bp  minor

POLITICAL EVENTS are CURATED in events_seed.csv, because "major" and "minor" are editorial
judgements that no API will make for you, and an automated feed (GDELT and similar) produces
enormous volume with no usable severity ranking. Every row carries a source URL so a reader
can check it. The seed is deliberately small and obvious - it is a starting point to extend,
not a claim to be comprehensive.

Licence: derived policy changes inherit the BIS terms. Curated rows are CC0 - they are dates
and plain facts - but each cites a source for verification.
"""
from pathlib import Path

import pandas as pd

from .common import DATA, write

SEED = Path(__file__).resolve().parent / "events_seed.csv"


def collect_policy_changes(min_bp=1.0):
    """Every change in a central bank policy rate, with size and direction."""
    src = DATA / "central_bank_rates.csv"
    assert src.exists(), "run the rates collector first - policy changes derive from it"
    r = pd.read_csv(src, parse_dates=["date"]).sort_values(["series", "date"])
    r["prev"] = r.groupby("series")["value"].shift()
    r["change_bp"] = (r["value"] - r["prev"]) * 100
    ch = r[r["change_bp"].abs() >= min_bp].dropna(subset=["change_bp"]).copy()

    ch["direction"] = ch["change_bp"].apply(lambda x: "hike" if x > 0 else "cut")
    size = ch["change_bp"].abs()
    ch["severity"] = pd.cut(size, [0, 25, 75, 1e9],
                            labels=["minor", "standard", "major"], right=False)
    ch["title"] = (ch["series"] + " " + ch["direction"] + " "
                   + size.round(0).astype(int).astype(str) + "bp to "
                   + ch["value"].round(2).astype(str) + "%")
    ch["category"] = "monetary policy"
    ch["value"] = ch["change_bp"]
    out = ch[["date", "series", "title", "category", "severity", "direction",
              "value", "iso2"]].copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out["unit"] = "basis points"
    out["source_url"] = "https://data.bis.org/topics/CBPOL"
    return out.sort_values("date")


def collect_political():
    """Curated political events. Small on purpose; extend events_seed.csv to grow it."""
    assert SEED.exists(), f"missing {SEED}"
    e = pd.read_csv(SEED)
    need = {"date", "title", "category", "severity", "region", "source_url"}
    missing = need - set(e.columns)
    assert not missing, f"events_seed.csv is missing columns: {missing}"
    bad = pd.to_datetime(e["date"], errors="coerce").isna()
    assert not bad.any(), f"unparseable dates in seed: {e.loc[bad, 'date'].tolist()}"
    allowed = {"major", "minor"}
    odd = set(e["severity"]) - allowed
    assert not odd, f"severity must be one of {allowed}, found {odd}"
    e["series"] = e["category"]
    e["value"] = 1.0                      # events are points, not magnitudes
    e["unit"] = "event"
    return e


def collect():
    pol = collect_policy_changes()
    write("policy_changes", pol,
          source="derived from data/central_bank_rates.csv (BIS)",
          licence="BIS - free use with attribution",
          note=("Every policy-rate change. severity by move size: >=75bp major, "
                ">=25bp standard, <25bp minor."))
    ev = collect_political()
    write("political_events", ev,
          source="curated; every row carries its own source_url",
          licence="CC0 for the compilation; see source_url per row",
          note="Hand-curated. Severity is editorial. Extend collectors/events_seed.csv.")
    return pol, ev


if __name__ == "__main__":
    collect()
