"""Dated, verifiable political and policy actions - the curated half of the event layer.

political_events is mostly Wikipedia year pages: broad, useful to plot against, and
editorially uneven. These are the opposite. Every row is a specific act by a specific
institution on a specific date, taken from that institution's own record:

  elections            ParlGov: every national election in ~37 democracies since 1900,
                       with turnout and seats. Elections are the cleanest natural
                       experiment in the repo - a scheduled date, an uncertain outcome.
  fed_communications   Every Federal Reserve Board press release since 2006, typed by the
                       Fed itself (Monetary Policy, Enforcement, Banking, ...). Twenty years
                       deep, which covers the financial crisis, ZIRP, taper, the 2022 hiking
                       cycle and the cuts after it.

WHAT WAS DROPPED AND WHY: OFAC sanctions were the obvious third source and do not work. The
SDN list is a SNAPSHOT of who is currently designated - the only dates in it are entity
attributes (dates of birth, passport validity), not the date an action was taken. Probed
SDN.CSV and SDN_ENHANCED.XML; neither carries a designation date, so there is no timeline to
extract and none is invented here.

Licences: ParlGov is free for research with attribution (Doring & Manow). Fed press releases
are US federal works, public domain.
"""
import json
from io import StringIO

import pandas as pd
import requests

from .common import UA, fetch, write

PARLGOV = "https://www.parlgov.org/data/parlgov-development_csv-utf-8/{table}.csv"
FED = "https://www.federalreserve.gov/json/ne-press.json"


def collect_elections():
    el = pd.read_csv(StringIO(fetch(PARLGOV.format(table="election"), binary=False)))
    co = pd.read_csv(StringIO(fetch(PARLGOV.format(table="country"), binary=False)))
    d = el.merge(co[["id", "name"]].rename(columns={"id": "country_id", "name": "country"}),
                 on="country_id", how="left")

    date = pd.to_datetime(d["date"], errors="coerce")
    ok = date.notna() & d["country"].notna()
    d, date = d[ok], date[ok]

    kind = d["election_type"].astype(str) if "election_type" in d.columns else "national"
    early = d["early"].fillna(0).astype(bool) if "early" in d.columns else False
    turnout = (pd.to_numeric(d.get("votes_cast"), errors="coerce")
               / pd.to_numeric(d.get("electorate"), errors="coerce") * 100)

    out = pd.DataFrame({
        "date": date.dt.strftime("%Y-%m-%d"),
        "title": d["country"] + " " + kind + " election",
        "series": "election",
        "country": d["country"],
        "category": "election",
        # An early election is a government falling, not a calendar event. That is the
        # subset worth overlaying on a chart, so it gets the higher severity.
        "severity": pd.Series(["major" if e else "standard" for e in early], index=d.index),
        "value": turnout.round(2),
        "unit": "turnout, percent of electorate",
        "source_url": d.get("wikipedia", pd.Series("", index=d.index)).fillna(""),
        "origin": "parlgov",
    }).sort_values("date")

    assert len(out) > 500, f"only {len(out)} elections"
    assert out["country"].nunique() >= 25, f"only {out['country'].nunique()} countries"
    t = out["value"].dropna()
    assert t.between(10, 100).mean() > 0.9, "turnout out of range - wrong columns divided"
    return write("elections", out,
                 source=PARLGOV.format(table="election"),
                 licence="Free for research with attribution. ParlGov (Doring & Manow).",
                 note=("National elections in ~37 democracies since 1900, with turnout where "
                       "the electorate is known. `severity` is major for early elections - a "
                       "government falling - and standard for scheduled ones, because that "
                       "is the distinction that matters when overlaying them on a price. "
                       "ParlGov's development export currently ends mid-2023."))


def collect_fed():
    # The file is served with a UTF-8 BOM and ends with an {"updateDate": ...} sentinel that
    # has none of the real fields, so it is filtered rather than parsed.
    raw = requests.get(FED, headers=UA, timeout=60)
    raw.raise_for_status()
    rows = [r for r in json.loads(raw.content.decode("utf-8-sig")) if "d" in r and "t" in r]

    d = pd.DataFrame(rows)
    date = pd.to_datetime(d["d"], errors="coerce", format="mixed")
    ok = date.notna()
    d, date = d[ok], date[ok]

    kind = d.get("pt", pd.Series("Other", index=d.index)).fillna("Other").astype(str)
    out = pd.DataFrame({
        "date": date.dt.strftime("%Y-%m-%d"),
        "title": d["t"].astype(str).str.strip(),
        "series": "Fed press release",
        "category": kind,
        # Monetary policy releases are the ones that move a curve. The rest are supervisory
        # and administrative notices, which are real but rarely priced.
        "severity": kind.eq("Monetary Policy").map({True: "major", False: "standard"}),
        "value": 1.0,
        "unit": "count",
        "source_url": "https://www.federalreserve.gov" + d.get("l", "").astype(str),
        "origin": "federalreserve.gov",
    }).sort_values("date")

    assert len(out) > 1000, f"only {len(out)} Fed releases"
    assert (out["category"] == "Monetary Policy").any(), "no monetary policy releases found"
    return write("fed_communications", out,
                 source=FED,
                 licence="US federal work, public domain. Attribute the Federal Reserve Board.",
                 note=("Every Federal Reserve Board press release the Fed publishes as JSON, "
                       "typed by the Fed itself. Goes back to 2006, so it covers the "
                       "financial crisis, ZIRP and both recent policy turns. Monetary Policy releases are "
                       "marked major; supervisory and administrative notices are standard."))


def collect():
    collect_elections()
    collect_fed()


if __name__ == "__main__":
    collect()
