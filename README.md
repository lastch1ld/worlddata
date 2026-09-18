# worlddata

Free, importable datasets about the world economy and the events around it, with a browser
UI to explore them. Every dataset is built by a script in `collectors/`, written to `data/`
as **CSV + JSON + metadata**, and validated before it lands.

**137,920 rows across 14 datasets, plus a 17-entry registry of external sources.**
No API key needed for any of it.

## Datasets in this repo

| dataset | rows | span | what it is |
|---|---|---|---|
| `central_bank_rates` | 25,043 | 1946–2026 | Official policy rate, monthly, 49 central banks |
| `population_by_country` | 17,195 | 1960–2024 | Total population, 265 countries and regions |
| `sp500_monthly` | 16,812 | 1871–2026 | Shiller S&P 500 incl. CAPE, earnings, dividends |
| `gdp_by_country` | 13,979 | 1960–2024 | GDP in current USD, 262 countries and regions |
| `inflation_by_country` | 13,778 | 1960–2024 | Consumer price inflation, 261 countries |
| `political_events` | 12,266 | 1946–2026 | World events: 22 curated + ~12.2k from Wikipedia year pages |
| `oil_wti_daily` | 9,502 | 1986–2026 | WTI crude spot, daily (US EIA) |
| `vix_daily` | 9,274 | 1990–2026 | CBOE Volatility Index, daily close |
| `oil_brent_daily` | 9,087 | 1987–2026 | Brent crude spot, daily (US EIA) |
| `policy_changes` | 6,741 | 1946–2026 | Every hike and cut, with size and direction |
| `gold_monthly` | 2,324 | 1833–2026 | Gold price, monthly |
| `us_10y_yield_monthly` | 880 | 1953–2026 | US 10-year Treasury yield, monthly |
| `commodities_annual` | 670 | 1960–2024 | Gold, oil, gas, metals (World Bank Pink Sheet) |
| `companies_top` | 369 | 2017–2023 | Largest companies by market cap, revenue, profit, assets |

## Use it

Every dataset exists in three forms:

```
data/<name>.csv         tidy long format, one observation per row
data/<name>.json        the same rows
data/<name>.meta.json   source URL, licence, span, series list, retrieval date
data/manifest.json      index of all datasets
data/registry.json      external datasets we index but do not copy
```

```python
import pandas as pd
rates = pd.read_csv("data/central_bank_rates.csv", parse_dates=["date"])
swiss = rates[rates.series == "Switzerland"]
```

```js
const rates = await (await fetch("data/central_bank_rates.json")).json();
```

Tidy long format (`date, series, value, …`) rather than one column per series: less pretty
to read, but adding a country or a commodity never changes the schema, which is what matters
when other people import it.

## Explore it

```bash
python -m http.server 8777
# open http://localhost:8777/web/index.html
```

Pick a dataset, pick series, set a year range. Political events overlay as dashed vertical
lines on any chart and list underneath with source links.

The UI handles four things that otherwise produce quietly wrong charts:

- **Mixed units** — gold is ~$2,000/oz and US gas is ~$3/mmbtu. On one linear axis gas is
  invisible, so the chart switches to log and says why.
- **Signed values** — a rate cut is negative basis points, and a log axis drops non-positive
  values silently. Central bank rates reach −0.75%, so log would hide the entire negative-rate
  era. Log is disabled for those datasets, not just discouraged.
- **Many rows per date** — `companies_top` holds ten companies per year per metric. Keying a
  chart on date alone keeps only the last one; rows are summed and labelled "combined".
- **Too many events** — 12,266 events as vertical lines is a black rectangle, not a chart.
  The overlay defaults to `major` only, caps drawing at 80 lines, and states how many were
  left out rather than truncating silently.

## The registry: what we index but do not copy

`data/registry.json` catalogues 17 open datasets, 9 of which are **not** vendored here.
That is deliberate, and it is the part that scales:

1. **Licences.** Much good open data is share-alike (CC BY-SA, ODbL). Copying it in makes
   this repo inherit those terms for everyone downstream. Our own collectors are permissive;
   mixing silently takes that away from people who import us.
2. **Staleness.** OWID updates daily. A copy in git is wrong within a week *and looks
   authoritative while being wrong*, which is worse than not having it.
3. **Size.** Git keeps every version of every file forever. A 200 MB CSV rebuilt weekly
   becomes tens of gigabytes of history nobody can clone.
4. **Duplication.** These repos already exist and are better maintained upstream.

So: vendor what is small, permissive and slow-moving; register everything else and fetch on
demand.

```python
from collectors.registry import catalogue, load
catalogue()                # everything indexed, with licence and publisher
df = load("owid-energy")   # fetched live from source, always current
```

`python build.py --verify-links` GETs every registered URL, because a registry of dead links
is worse than no registry. All 17 currently resolve.

## Rebuild it

```bash
pip install -r requirements.txt
python build.py                 # fetch everything, rebuild data/, regenerate the manifest
python build.py --check         # validate what's committed, no network
python build.py --verify-links  # check every registry URL still resolves
```

`--check` verifies row counts match the metadata, columns haven't drifted, dates parse, and
every dataset records a source and a licence. That is the failure mode worth catching: a
dataset that quietly truncates or changes shape breaks everyone importing it.

## Sources and licences

| dataset | source | licence |
|---|---|---|
| central bank rates, policy changes | [BIS policy rates](https://data.bis.org/topics/CBPOL) | Free use with attribution |
| commodities (annual) | [World Bank "Pink Sheet"](https://www.worldbank.org/en/research/commodity-markets) | CC BY 4.0 |
| GDP | [datasets/gdp](https://github.com/datasets/gdp) (World Bank) | CC BY 4.0 |
| population, inflation, oil, gold, VIX, S&P 500, 10y yield | [github.com/datasets](https://github.com/datasets) | ODC-PDDL-1.0 |
| companies | Wikipedia (Forbes Global 2000, largest by revenue) | CC BY-SA 4.0 |
| political events | Curated seed + English Wikipedia year pages | CC0 compilation; Wikipedia text CC BY-SA 4.0 |

**Code is MIT. Data is not** — see `LICENSE`. In particular the Wikipedia-derived company
and event data is CC BY-SA, which is share-alike.

Where an official bulk file exists it is used instead of scraping. BIS and World Bank files
are authoritative, carry explicit units, and stay correct when revised.

## Known limits

**Companies: top 10 per year, not top 100.** Free sources do not carry top 100 per year on
three metrics. What exists: Forbes Global 2000 top 10 per year (sales, profit, assets) plus
a current top 50 by revenue. Every row records `list_depth`, and different depths live in
different series so they never get summed together — without that, revenue appeared to jump
6× in one year purely because the list got deeper. A genuine top 100 per year needs SEC
EDGAR bulk filings (free, but you assemble market cap from shares × price per company per
year) or a paid vendor.

**Political events mix two qualities.** 22 rows are hand-curated and verified; ~12,200 are
parsed from English Wikipedia year pages. Scraped rows get severity from the stated
`HIGH_IMPACT` rule in `events_wiki.py` (~11% come out `major`) — a mechanical filter, not a
human judgement. The `origin` column says which is which, and curated rows win on conflict.
English Wikipedia over-represents the anglophone world, and "notable enough for the year
page" is itself a volunteer judgement. Treat it as a broad timeline to plot against, not a
register of record.

About 39% of scraped events land in category `other` — mostly genuinely miscellaneous
(sport, culture, product launches). `collect()` asserts the share stays under 55%, so a
Wikipedia markup change that breaks classification fails the build instead of quietly
shipping unclassified data.

**Policy-change severity is a rule, not a judgement:** ≥75bp major, ≥25bp standard, <25bp
minor. Stated so you can disagree with it.

**Country-level series use source country names,** not a harmonised code. `country-codes` is
in the registry if you need to join across sources.

## Adding a dataset

Write `collectors/yourthing.py` with a `collect()` that ends in `write(name, df, source,
licence, note)`. `write` validates the frame and emits all three files. Add it to `build.py`.
The UI picks it up from the manifest automatically — nothing to register.

To add a *reference* to someone else's data instead, append an entry to `SEED` in
`collectors/registry.py` with a direct link to a machine-readable file (not a homepage) and
run `--verify-links`.
