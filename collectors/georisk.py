"""Geopolitical risk indices (Caldara & Iacoviello), monthly to 1900 and daily to 1985.

This is the most direct "world happenings, quantified" series that exists for free. It
counts geopolitical language in major newspapers and normalises it, so a war scare, a
terrorist attack or a nuclear threat shows up as a measurable level rather than as an
anecdote you have to hand-code.

Three things make it well suited to correlating events with markets:

  THREATS vs ACTS are separate (GPRT / GPRA). Markets usually move on the threat and
  recover on the act, so collapsing them loses the interesting half.
  PER-COUNTRY indices exist for 44 countries (GPRC_*), so you can ask whether a shock is
  local or global instead of assuming.
  LABELLED SPIKES ship in the daily file - the authors annotate notable dates ("London
  Bombings 7/7", "Russia / Ukraine Tensions"). Those are academically curated event
  markers, which is a higher standard than the Wikipedia-derived rows in political_events,
  so they are emitted separately as `georisk_events`.

Conflict databases were checked first and all now require registration: UCDP returns 401,
EM-DAT 404 without an account, ACLED needs a key. GPR is the free substitute and, for
"did markets notice", arguably the better one - it measures attention, not casualties.

Licence: free for research with attribution to Caldara & Iacoviello (2022), "Measuring
Geopolitical Risk", American Economic Review. https://www.matteoiacoviello.com/gpr.htm
"""
import io

import pandas as pd

from .common import fetch, write

MONTHLY = "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls"
DAILY = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
CITE = "Caldara & Iacoviello (2022), Measuring Geopolitical Risk, AER"

HEADLINE = {
    "GPR": ("Geopolitical risk (global)", "index"),
    "GPRT": ("Geopolitical threats", "index"),
    "GPRA": ("Geopolitical acts", "index"),
    "GPRH": ("Geopolitical risk (historical)", "index"),
    "GPRHT": ("Geopolitical threats (historical)", "index"),
    "GPRHA": ("Geopolitical acts (historical)", "index"),
}


def collect_monthly():
    d = pd.read_excel(io.BytesIO(fetch(MONTHLY)))
    d.columns = [str(c) for c in d.columns]
    assert "month" in d.columns, "GPR monthly file changed: no 'month' column"
    rows = []
    for col, (label, unit) in HEADLINE.items():
        if col not in d.columns:
            continue
        v = pd.to_numeric(d[col], errors="coerce")
        keep = v.notna()
        rows.append(pd.DataFrame({
            "date": pd.to_datetime(d.loc[keep, "month"]).dt.strftime("%Y-%m-%d"),
            "series": label, "scope": "global", "value": v[keep], "unit": unit}))
    for col in [c for c in d.columns if c.startswith("GPRC_")]:
        iso3 = col.split("_", 1)[1]
        v = pd.to_numeric(d[col], errors="coerce")
        keep = v.notna()
        if keep.sum() < 50:
            continue
        rows.append(pd.DataFrame({
            "date": pd.to_datetime(d.loc[keep, "month"]).dt.strftime("%Y-%m-%d"),
            "series": f"GPR {iso3}", "scope": iso3, "value": v[keep], "unit": "index"}))
    out = pd.concat(rows, ignore_index=True).sort_values(["series", "date"])
    n_country = out["scope"].nunique() - 1
    assert n_country >= 30, f"only {n_country} country indices found"
    return write("geopolitical_risk", out,
                 source=MONTHLY, licence=f"Free for research with attribution. {CITE}",
                 note=("Monthly geopolitical risk index from newspaper text, 1900 onwards. "
                       "Threats (GPRT) and acts (GPRA) are separate on purpose - markets "
                       f"tend to move on the threat. {n_country} country indices included."))


def collect_daily():
    d = pd.read_excel(io.BytesIO(fetch(DAILY)))
    d.columns = [str(c) for c in d.columns]
    datecol = "date" if "date" in d.columns else "DAY"
    dt = pd.to_datetime(d[datecol], errors="coerce", format="mixed")

    wanted = {"GPRD": ("Geopolitical risk (daily)", "index"),
              "GPRD_ACT": ("Geopolitical acts (daily)", "index"),
              "GPRD_THREAT": ("Geopolitical threats (daily)", "index"),
              "GPRD_MA7": ("Geopolitical risk, 7-day average", "index"),
              "GPRD_MA30": ("Geopolitical risk, 30-day average", "index")}
    rows = []
    for col, (label, unit) in wanted.items():
        if col not in d.columns:
            continue
        v = pd.to_numeric(d[col], errors="coerce")
        keep = v.notna() & dt.notna()
        rows.append(pd.DataFrame({"date": dt[keep].dt.strftime("%Y-%m-%d"),
                                  "series": label, "scope": "global",
                                  "value": v[keep], "unit": unit}))
    out = pd.concat(rows, ignore_index=True).sort_values(["series", "date"])
    write("geopolitical_risk_daily", out,
          source=DAILY, licence=f"Free for research with attribution. {CITE}",
          note="Daily geopolitical risk, 1985 onwards, with threat/act split and moving averages.")

    # The authors label notable spikes. These are curated by researchers, so they are a
    # cleaner event source than the Wikipedia-derived rows and are kept separate.
    if "event" in d.columns:
        ev = d[d["event"].notna()].copy()
        ev_dt = pd.to_datetime(ev[datecol], errors="coerce", format="mixed")
        gp = pd.to_numeric(ev.get("GPRD"), errors="coerce")
        out_ev = pd.DataFrame({
            "date": ev_dt.dt.strftime("%Y-%m-%d"),
            "title": ev["event"].astype(str).str.strip(),
            "series": "geopolitical spike",
            "category": "conflict",
            "severity": "major",
            "value": gp.fillna(1.0),
            "unit": "GPR index on the day",
            "source_url": "https://www.matteoiacoviello.com/gpr.htm",
            "origin": "caldara-iacoviello",
        }).dropna(subset=["date"]).sort_values("date")
        assert len(out_ev) > 10, f"only {len(out_ev)} labelled events found"
        write("georisk_events", out_ev,
              source=DAILY, licence=f"Free for research with attribution. {CITE}",
              note=("Dates the GPR authors annotated as notable geopolitical spikes, with "
                    "the index level on the day. Researcher-curated, so a higher standard "
                    "than the Wikipedia-derived rows in political_events."))
    return out


def collect():
    collect_monthly()
    collect_daily()


if __name__ == "__main__":
    collect()
