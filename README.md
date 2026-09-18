# worlddata

Free, importable datasets about the world economy, with a browser UI to explore them.
Every dataset is built by a script in `collectors/`, written to `data/` as **CSV + JSON +
metadata**, and validated before it lands.

**32,845 rows across 5 datasets.** No API key needed for any of it.

## What's in here

| dataset | rows | span | what it is |
|---|---|---|---|
| `central_bank_rates` | 25,043 | 1946–2026 | Official policy rate, monthly, 49 central banks |
| `policy_changes` | 6,741 | 1946–2026 | Every hike and cut, with size and direction |
| `commodities_annual` | 670 | 1960–2024 | Gold, oil (Brent/WTI/Dubai), gas (US/EU/Japan LNG), metals |
| `companies_top` | 369 | 2017–2023 | Largest companies by market cap, revenue, profit, assets |
| `political_events` | 22 | 1997–2024 | Curated major political and financial events |

## Use it

Every dataset exists in three forms:

```
data/<name>.csv         tidy long format, one observation per row
data/<name>.json        the same rows
data/<name>.meta.json   source URL, licence, span, series list, retrieval date
data/manifest.json      index of all datasets
```

```python
import pandas as pd
rates = pd.read_csv("data/central_bank_rates.csv", parse_dates=["date"])
swiss = rates[rates.series == "Switzerland"]
```

```js
const rates = await (await fetch("data/central_bank_rates.json")).json();
```

Tidy long format (`date, series, value, …`) rather than one column per series: it is less
pretty to read, but adding a country or a commodity never changes the schema, which matters
when other people import it.

## Explore it

```bash
python -m http.server 8777
# open http://localhost:8777/web/index.html
```

Pick a dataset, pick series, set a year range. Political events overlay as dashed vertical
lines on any chart, and list underneath with source links.

The UI handles three things that otherwise produce quietly wrong charts:

- **Mixed units** — gold is ~$2,000/oz and US gas is ~$3/mmbtu. On one linear axis gas is
  invisible, so the chart switches to log and says why.
- **Signed values** — a rate cut is negative basis points, and a log axis drops non-positive
  values silently. Log is disabled for those datasets, not just discouraged.
- **Many rows per date** — `companies_top` holds ten companies per year per metric. Keying
  a chart on date alone keeps only the last one; rows are summed and labelled "combined".

## Rebuild it

```bash
pip install -r requirements.txt
python build.py           # fetch everything, rebuild data/, regenerate the manifest
python build.py --check   # validate what's committed, no network
```

`--check` verifies row counts match the metadata, columns haven't drifted, dates parse and
every dataset records a source and a licence. That is the failure mode worth catching: a
dataset that quietly truncates or changes shape breaks everyone importing it.

## Sources and licences

| dataset | source | licence |
|---|---|---|
| central bank rates, policy changes | [BIS policy rates](https://data.bis.org/topics/CBPOL) | Free use with attribution |
| commodities | [World Bank "Pink Sheet"](https://www.worldbank.org/en/research/commodity-markets) | CC BY 4.0 |
| companies | Wikipedia (Forbes Global 2000, largest by revenue) | CC BY-SA 4.0 |
| political events | Curated; every row carries `source_url` | CC0 for the compilation |

Where an official bulk file exists it is used instead of scraping. The BIS and World Bank
files are authoritative, carry explicit units, and stay correct when revised — scraped price
sites do none of those.

## Known limits

**Companies: top 10 per year, not top 100.** Free sources do not carry top 100 per year on
three metrics. What exists: Forbes Global 2000 top 10 per year (sales, profit, assets),
plus a current top 50 by revenue. Every row records `list_depth` so you always know how deep
the list goes, and different depths are kept in different series so they never get summed
together. Getting to a genuine top 100 per year needs SEC EDGAR bulk filings (free, but you
assemble market cap from shares × price per company per year) or a paid vendor.

**Political events are editorial.** "Major" and "minor" are judgements, not data. The seed
list is deliberately small and obvious, and every row cites a source. Extend
`collectors/events_seed.csv` — it is a plain CSV with a validated schema.

**Policy-change severity is a rule, not a judgement:** ≥75bp major, ≥25bp standard, <25bp
minor. Stated so you can disagree with it.

## Adding a dataset

Write `collectors/yourthing.py` with a `collect()` that ends in `write(name, df, source,
licence, note)`. `write` validates the frame and emits all three files. Add it to `build.py`.
The UI picks it up from the manifest automatically — nothing to register.
