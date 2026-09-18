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

POLITICAL EVENTS come from two places, merged:

  events_seed.csv         hand-curated, verified, severity set by a human. Wins on conflict.
  Wikipedia year pages    ~12,000 dated events, 1946 onwards, parsed by events_wiki.py

The scraped rows carry a severity assigned by the stated HIGH_IMPACT rule in events_wiki.py,
not by a person - about 11% come out "major". That is a mechanical filter, not a judgement,
and it is in the source so you can change it. GDELT and similar feeds were rejected for the
opposite reason: enormous volume with no usable severity ranking at all.

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


def collect_political(scrape=True, start=1946, polite=0.4):
    """Curated events, plus the much larger set parsed from Wikipedia year pages.

    The curated rows are hand-verified and win on conflict: if the same event appears in
    both, the curated severity, region and source survive. Scraped rows fill in everything
    the seed does not cover, which is almost all of it.
    """
    curated = _read_seed()
    curated["origin"] = "curated"
    if not scrape:
        return curated

    from . import events_wiki
    wiki = events_wiki.collect(start=start, polite=polite)
    wiki["origin"] = "wikipedia-year-page"
    wiki["series"] = wiki["category"]
    wiki["value"] = 1.0
    wiki["unit"] = "event"

    # Drop scraped rows that duplicate a curated one. Same day plus a shared distinctive
    # word is enough: the two sources word things differently, so exact-title matching
    # would let near-duplicates through.
    key = set()
    for _, r in curated.iterrows():
        words = {w.lower() for w in str(r["title"]).split() if len(w) > 6}
        key.add((str(r["date"])[:10], frozenset(words)))
    def dup(row):
        w = {x.lower() for x in str(row["title"]).split() if len(x) > 6}
        for d, kw in key:
            if d == str(row["date"])[:10] and (w & kw):
                return True
        return False
    wiki = wiki[~wiki.apply(dup, axis=1)]

    both = pd.concat([curated, wiki], ignore_index=True)
    return both.sort_values("date").reset_index(drop=True)


def _read_seed():
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
    n_cur = int((ev["origin"] == "curated").sum())
    write("political_events", ev,
          source="collectors/events_seed.csv (curated) + English Wikipedia year pages",
          licence="CC0 for the curated compilation; Wikipedia text CC BY-SA 4.0",
          note=(f"{n_cur} hand-curated rows (verified, win on conflict) plus "
                f"{len(ev) - n_cur} parsed from Wikipedia year articles. Severity for "
                "scraped rows follows the HIGH_IMPACT rule in events_wiki.py, not a "
                "human judgement. Extend collectors/events_seed.csv to add curated rows."))
    return pol, ev


if __name__ == "__main__":
    collect()
