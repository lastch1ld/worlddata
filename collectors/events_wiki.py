"""Political and world events, parsed from Wikipedia year pages.

Wikipedia keeps one article per year with an "Events" section: month-by-month, dated,
already filtered to what editors considered notable. That editorial filter is the reason
this is usable at all - an unfiltered feed like GDELT produces millions of rows with no
severity ranking, which is worse than useless for a timeline.

SEVERITY IS A STATED RULE, NOT A JUDGEMENT
Everything on a year page is already "notable", so the default is `minor`. An event is
promoted to `major` only if its text matches HIGH_IMPACT below - war, invasion, coup,
pandemic, financial collapse and so on. The rule lives in this file so you can disagree
with it, edit the list and rebuild. Hand-curated rows in events_seed.csv keep the severity
they were given there and win on conflict.

WHAT THIS IS NOT
It is not exhaustive and not neutral. English Wikipedia over-represents the anglophone
world, and "notable enough for the year page" is itself a judgement made by volunteers.
Treat it as a broad timeline to plot against, not as a register of record.
"""
import re
import time

import pandas as pd

from .common import fetch

MONTHS = ("January|February|March|April|May|June|July|August|September|October|"
          "November|December")
MONTH_NUM = {m: i + 1 for i, m in enumerate(
    "January February March April May June July August September October "
    "November December".split())}

# First match wins, so order matters: more specific categories go first.
#
# Note every stem ends in \w* or an explicit plural. An earlier version used \bbomb\b and
# \beruption\b, which do not match "bombings" or "eruptions" - the forms Wikipedia actually
# writes - and 62% of events fell through to "other" as a result. Match stems, not words.
CATEGORIES = [
    ("conflict", r"\b(wars?|warfare|invad\w*|invasion\w*|troops|militar\w*|"
                 r"battles?|airstrikes?|bomb\w*|attack\w*|terror\w*|insurgen\w*|"
                 r"ceasefires?|offensive|missiles?|shootings?|massacres?|"
                 r"hostages?|militants?|rebel\w*|coup\b|genocide|assassinat\w*)"),
    ("financial", r"\b(stock market|financial crisis|recession|defaults?\b|bankrupt\w*|"
                  r"bailouts?|devalu\w*|inflation|currenc\w+|"
                  r"bank\w* (?:crisis|collapse|run)|debt crisis|euro\b|IMF\b|World Bank|"
                  r"merger|acquisition|IPO\b)"),
    ("election", r"\b(elect\w*|referend\w*|inaugurat\w*|sworn in|becomes? (?:the )?"
                 r"(?:president|prime minister|chancellor)|resign\w* as|impeach\w*|"
                 r"takes office|parliament\w* vote)"),
    ("policy", r"\b(treat(?:y|ies)|protocols?|accords?|agreements?|signs? into law|"
               r"sanction\w*|tariffs?|summit|constitution\w*|legislat\w*|resolution|"
               r"joins? the|withdraw\w* from|independence|goes into effect|"
               r"comes? into force|member states?|ratif\w*|bans?\b|legali[sz]\w*)"),
    ("disaster", r"\b(earthquakes?|tsunamis?|hurricanes?|cyclones?|typhoons?|"
                 r"floods?|wildfires?|erupt\w*|volcan\w*|famine|drought|landslides?|"
                 r"crash(?:es|ed|ing)?\b|derail\w*|capsiz\w*|fatalities|"
                 r"kill(?:s|ed|ing)? (?:at least |nearly |more than )?\d)"),
    ("health", r"\b(pandemics?|epidemics?|outbreaks?|virus\w*|vaccin\w*|"
               r"WHO declares|diseases?|infect\w*|quarantin\w*)"),
    ("science", r"\b(spacecraft|satellites?|launch\w*|rover|probe\b|space\b|"
                r"moon\b|mars\b|telescopes?|orbit\w*|astronauts?|discover\w*|"
                r"collider|genome)"),
    ("legal", r"\b(stands? trial|convict\w*|sentenc\w*|indict\w*|courts?\b|tribunals?|"
              r"crimes against humanity|war crimes|verdict|acquitt\w*|extradit\w*|"
              r"arrest\w*|charged with)"),
]

HIGH_IMPACT = re.compile(
    r"\b(world war|invasion|invades|declares? war|coup\b|revolution|assassinat\w*|"
    r"pandemic|genocide|nuclear (?:test|attack|weapon)|financial crisis|great recession|"
    r"stock market crash|collapse of|dissolv\w*|independence|peace treaty|armistice|"
    r"impeach\w*|resigns? as|overthrow\w*|declares? independence|"
    r"kill(?:s|ed|ing)? (?:at least |nearly |more than )?\d{3,})", re.I)

CLEAN_TAGS = re.compile(r"<sup.*?</sup>|<style.*?</style>|<.*?>", re.S)
CITATION = re.compile(r"\[\d+\]|\[citation needed\]", re.I)
STOP_SECTION = r'id="(Births|Deaths|Publications|Nobel|Nobel_Prizes|See_also|References)'


def _plain(fragment):
    t = CLEAN_TAGS.sub("", fragment)
    t = CITATION.sub("", t)
    return re.sub(r"\s+", " ", t).replace("–", "-").replace("—", "-").strip()


def classify(text):
    for name, pat in CATEGORIES:
        if re.search(pat, text, re.I):
            return name
    return "other"


def parse_year(year, polite=0.4):
    """Dated events from one Wikipedia year article."""
    url = f"https://en.wikipedia.org/wiki/{year}"
    try:
        html = fetch(url, binary=False)
    except Exception:
        return []
    time.sleep(polite)          # only bites on a cache miss

    sec = re.search(r'id="Events"(.*?)' + STOP_SECTION, html, re.S)
    if not sec:
        return []
    items = re.findall(r"<li[^>]*>(.*?)</li>", sec.group(1), re.S)

    out, month, day = [], None, None
    for raw in items:
        text = _plain(raw)
        if not text or len(text) < 12:
            continue
        m = re.match(rf"^({MONTHS})\s+(\d{{1,2}})\s*[-:]?\s*(.*)$", text)
        if m:
            month, day, body = m.group(1), int(m.group(2)), m.group(3)
        else:
            m2 = re.match(rf"^({MONTHS})\s*[-:]?\s*(.*)$", text)
            if m2:
                month, day, body = m2.group(1), 1, m2.group(2)
            elif month is None:
                continue
            else:
                body = text            # continuation bullet under the previous date
        body = body.strip(" -:")
        if len(body) < 12:
            continue
        try:
            safe_day = min(day, 28) if month == "February" else min(day, 30)
            date = pd.Timestamp(year=year, month=MONTH_NUM[month],
                                day=safe_day).strftime("%Y-%m-%d")
        except Exception:
            continue
        out.append({"date": date, "title": body[:300], "category": classify(body),
                    "severity": "major" if HIGH_IMPACT.search(body) else "minor",
                    "region": "", "source_url": url})
    return out


def collect(start=1946, end=None, polite=0.4, verbose=True):
    end = end or pd.Timestamp.today().year
    rows = []
    for y in range(start, end + 1):
        rows.extend(parse_year(y, polite))
        if verbose and y % 10 == 0:
            print(f"    {y}: {len(rows):,} events so far", flush=True)
    df = pd.DataFrame(rows).drop_duplicates(subset=["date", "title"])
    assert len(df) > 500, f"only parsed {len(df)} events - Wikipedia markup may have changed"
    share_other = (df["category"] == "other").mean()
    assert share_other < 0.55, (
        f"{share_other:.0%} of events are uncategorised - the CATEGORIES patterns have "
        "drifted from the source text")
    return df
