# worlddata

Free, importable datasets about the world economy and the events around it, with a browser
UI to explore them. Every dataset is built by a script in `collectors/`, written to `data/`
as **CSV + JSON + metadata**, and validated before it lands.

**1,125,847 rows across 31 datasets, plus a 51-entry registry of external sources.**
No API key needed for any of it.

The organising question is: *what happened in the world, and did money notice?* So the
datasets come in three kinds, meant to be plotted against each other:

- **Things that happened** — political events, elections, central bank press releases,
  geopolitical risk, policy changes.
- **How uncertain everyone was about what would happen next** — economic policy uncertainty
  by country and category, trade policy uncertainty, the IMF world index, supply chain
  pressure.
- **What money did about it** — rates, FX, credit spreads, equities, commodities, crypto,
  and speculative positioning.

The third kind is mostly prices. `cftc_positioning` is the exception and the most useful
single addition: it is the only free source here for what traders were actually holding,
rather than the level at which the market cleared.

## Datasets in this repo

| dataset | rows | span | what it is |
|---|---|---|---|
| `market_drivers` | 382,941 | 1919–2026 | 56 macro/market series from FRED, grouped by transmission channel |
| `euro_area_drivers` | 274,912 | 1981–2026 | ECB policy rates, AAA curve, HICP, M3 and daily EUR FX for 31 currencies |
| `cftc_positioning` | 105,054 | 1986–2026 | Weekly speculative positioning in 30 futures contracts |
| `geopolitical_risk_daily` | 76,160 | 1985–2026 | Daily geopolitical risk index, threat/act split, moving averages |
| `uncertainty_world` | 36,603 | 1952–2024 | IMF World Uncertainty Index, quarterly, 143 countries |
| `geopolitical_risk` | 28,060 | 1900–2026 | Monthly geopolitical risk, global + 44 country indices |
| `central_bank_rates` | 25,043 | 1945–2026 | Official policy rate, monthly, 49 central banks |
| `trade_policy_uncertainty` | 24,540 | 1960–2026 | Trade policy uncertainty, monthly and daily |
| `uncertainty_epu` | 22,184 | 1976–2026 | Economic policy uncertainty: 21 countries + US by category |
| `crypto_daily` | 18,853 | 2012–2026 | Daily close and volume for five crypto pairs |
| `population_by_country` | 17,195 | 1960–2024 | Total population, 265 countries and regions |
| `sp500_monthly` | 16,812 | 1871–2026 | Shiller S&P 500 incl. CAPE, earnings, dividends |
| `gdp_by_country` | 13,979 | 1960–2023 | GDP in current USD, 262 countries and regions |
| `inflation_by_country` | 13,778 | 1961–2023 | Consumer price inflation, 261 countries |
| `political_events` | 12,266 | 1946–2026 | World events: 22 curated + ~12.2k from Wikipedia year pages |
| `oil_wti_daily` | 9,502 | 1986–2026 | WTI crude spot, daily (US EIA) |
| `vix_daily` | 9,274 | 1990–2026 | CBOE Volatility Index, daily close |
| `oil_brent_daily` | 9,087 | 1987–2026 | Brent crude spot, daily (US EIA) |
| `causaldata_texas` | 7,330 | 1985–2000 | US state panel: prison populations by race plus covariates (synthetic-control example) |
| `policy_changes` | 6,741 | 1946–2026 | Every hike and cut, with size and direction |
| `causaldata_gapminder` | 5,112 | 1952–2007 | Life expectancy, population, GDP per capita for 142 countries, 5-yearly |
| `fed_communications` | 4,630 | 2006–2026 | Every Fed Board press release, typed by the Fed |
| `gold_monthly` | 2,324 | 1833–2026 | Gold price, monthly |
| `elections` | 1,027 | 1900–2023 | National elections in 37 democracies, with turnout |
| `us_10y_yield_monthly` | 880 | 1953–2026 | US 10-year Treasury yield, monthly |
| `commodities_annual` | 670 | 1960–2025 | Gold, oil, gas, metals (World Bank Pink Sheet) |
| `companies_top` | 369 | 2017–2023 | Largest companies by market cap, revenue, profit, assets |
| `supply_chain_pressure` | 344 | 1998–2026 | NY Fed Global Supply Chain Pressure Index |
| `causaldata_organ_donations` | 162 | 2010–2012 | Quarterly organ-donation rate, 27 US states, around California's 2011 policy change |
| `georisk_events` | 11 | 1986–2022 | Geopolitical spikes labelled by the GPR authors |
| `causaldata_snow` | 4 | 1849–1854 | John Snow's cholera death rates by water supplier |

### `market_drivers`: organised by how a shock reaches a price

Series are grouped by **transmission channel** rather than by topic, because "what moved
this" is a question about routes, not categories. Filter on the `channel` column:

| channel | what it is | examples |
|---|---|---|
| `fx` | the price of money against other money | USD/EUR, CHF/USD, USD broad index |
| `rates` | the curve everything is discounted against | fed funds, 2y/10y/30y, 10y−2y |
| `credit` | willingness to lend | high-yield OAS, IG OAS, NFCI, STLFSI4 |
| `liquidity` | money supply and the central bank balance sheet | M2, WALCL, reverse repo, TGA |
| `inflation` | realised, and market-**implied** | CPI, 10y breakeven, 10y real yield |
| `activity` | the real economy | unemployment, payrolls, IP, claims, GDP |
| `housing` | the largest asset most households own | Case-Shiller, starts, 30y mortgage |
| `trade` | cross-border flows and the balance | trade balance, federal debt / GDP |
| `equity` | the thing being explained | S&P 500, Nasdaq, Dow, VIX |
| `commodity` | physical inputs that show up in costs | WTI, Brent, Henry Hub gas |
| `uncertainty` | policy and equity-market uncertainty | EPU, equity-market uncertainty |

Breakevens and real yields are in here deliberately: they are what the market *expects*,
priced continuously, rather than what a statistical agency measured two months ago.

**Dead series are dropped, not carried forward flat.** Several FRED ids still resolve long
after they stopped publishing — TEDRATE ends in 2022 and would look like a flat line to
2026. Anything whose last observation is older than `STALE_DAYS` (400) is dropped with a
printed note. One id (`WILL5000IND`) 404s and is skipped; 56 of 57 land.

### `euro_area_drivers` concatenates with `market_drivers`

It uses the same `channel` column on purpose, because FRED's free non-US coverage is thin and
`market_drivers` alone makes every cross-asset question implicitly a question about America:

```python
both = pd.concat([
    pd.read_csv("data/market_drivers.csv"),
    pd.read_csv("data/euro_area_drivers.csv"),
])
rates = both[both.channel == "rates"]
```

ECB FX is EUR-based and fixed once daily — reference rates, not tradeable quotes. RUB ends in
March 2022 where the ECB suspended publication, and is left ending there rather than filled.

### The event sources are not the same quality, so they stay apart

Four of them, in descending order of how much you should trust a single row:

| dataset | rows | what it is |
|---|---|---|
| `fed_communications` | 4,630 | The Fed's own press releases, typed by the Fed |
| `elections` | 1,027 | ParlGov: dated national elections with turnout |
| `georisk_events` | 11 | Dates the GPR authors annotated as notable spikes |
| `political_events` | 12,266 | 22 hand-verified rows + ~12,200 parsed from Wikipedia |

They are kept separate rather than merged, because folding a curated register into a scraped
one loses the only thing that made it worth having. The `origin` column says which is which.

Conflict databases were checked first and all now require registration — UCDP returns 401,
EM-DAT 404 without an account, ACLED needs a key. GPR is the free substitute and, for the
question "did markets notice", arguably the better one: it measures attention, not casualties.

**OFAC sanctions were tried and dropped.** The SDN list is a snapshot of who is *currently*
designated; the only dates in it are entity attributes — dates of birth, passport validity —
not the date an action was taken. Both `SDN.CSV` and `SDN_ENHANCED.XML` were checked. There is
no timeline in there to extract, so none was invented.

## Use it

Every dataset exists in three forms:

```
data/<name>.csv         tidy long format, one observation per row
data/<name>.json        the same rows (thinned above 60k rows — see below)
data/<name>.meta.json   source URL, licence, span, series list, retrieval date
data/manifest.json      index of all datasets
data/registry.json      external datasets we index but do not copy
```

```python
import pandas as pd
mk = pd.read_csv("data/market_drivers.csv", parse_dates=["date"])
credit = mk[mk.channel == "credit"]
```

```js
const gpr = await (await fetch("data/geopolitical_risk.json")).json();
```

```bash
# plain JDK 17+, no build tool: latest value of every series in a CSV
java examples/java/LatestValues.java data/central_bank_rates.csv
```

Tidy long format (`date, series, value, …`) rather than one column per series: less pretty
to read, but adding a country or a commodity never changes the schema, which is what matters
when other people import it.

### The CSV is canonical. The JSON is for the browser.

Above `JSON_ROW_CAP` (60,000 rows) the JSON is **thinned to the last observation per series
per month**. `market_drivers` as raw JSON is 45 MB, which doubles the repo and hangs the page
before it draws anything; thinned it is 30,593 rows and loads in about 2.5 s.

That is enough to chart and useless for analysis, so it is recorded rather than hidden: every
`meta.json` carries `json_rows`, `json_thinned`, and a `json_note` when true, and
`build.py --check` asserts they match the files. Four of 31 datasets are thinned
(`market_drivers`, `euro_area_drivers`, `cftc_positioning`, `geopolitical_risk_daily`).
**Use the CSV for anything real** — it is always complete.

## Explore it

```bash
python -m http.server 8777
```

Then open `http://localhost:8777/web/index.html`. Pick a dataset, pick series, set a year
range. Political events overlay as dashed vertical lines on any chart and list underneath
with source links.

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

`data/registry.json` catalogues 51 open datasets, 39 of which are **not** vendored here.
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

34 of the entries are the [`causaldata`](https://cran.r-project.org/package=causaldata) teaching
datasets (`causaldata-nsw-mixtape`, `causaldata-castle`, `causaldata-nhefs`, ...): mostly
cross-sectional microdata for causal-inference examples. `load()` reads both CSV and Stata
`.dta` entries. Four have a real time axis and are also vendored as `causaldata_*` datasets
(`gapminder`, `texas`, `organ_donations`, `snow`). Three time-indexed ones are deliberately
left registry-only: `avocado` (Kaggle) and `google_stock` (tidyquant/Yahoo Finance) have
third-party terms the package does not state, and `castle` identifies states only by a
numeric id.

`python build.py --verify-links` GETs every registered URL, because a registry of dead links
is worse than no registry. All 51 currently resolve.

## Rebuild it

```bash
pip install -r requirements.txt
```

```bash
python build.py
```

`--check` validates what is committed without touching the network; `--verify-links` checks
every registry URL still resolves. `--check` verifies row counts match the metadata, columns
haven't drifted, dates parse, JSON row counts and thinning flags are accurate, every dataset
records a source and a licence, and every series the UI names as a default actually exists
(the UI falls back silently otherwise, so a renamed series would degrade the opening view
without any error). That is the failure mode worth catching: a dataset
that quietly truncates or changes shape breaks everyone importing it.

## Sources and licences

| dataset | source | licence |
|---|---|---|
| market drivers | [FRED](https://fred.stlouisfed.org) (see `fred_id` per row) | Mostly US federal works (public domain); ICE BofA OAS indices carry ICE terms |
| euro area drivers | [ECB Data Portal](https://data.ecb.europa.eu/) (see `ecb_key` per row) | Free use with attribution to the ECB |
| CFTC positioning | [CFTC public reporting](https://publicreporting.cftc.gov/) | US federal work, public domain |
| uncertainty (EPU, TPU, WUI) | [policyuncertainty.com](https://www.policyuncertainty.com/), [worlduncertaintyindex.com](https://worlduncertaintyindex.com/) | Free for research with attribution (Baker/Bloom/Davis; Caldara et al.; Ahir/Bloom/Furceri) |
| supply chain pressure | [NY Fed GSCPI](https://www.newyorkfed.org/research/policy/gscpi) | Free use with attribution to the FRBNY |
| crypto | [Bitstamp public API](https://www.bitstamp.net/api/) | Free to use, attribute Bitstamp |
| elections | [ParlGov](https://www.parlgov.org/) | Free for research with attribution (Döring & Manow) |
| Fed communications | [federalreserve.gov](https://www.federalreserve.gov/json/ne-press.json) | US federal work, public domain |
| geopolitical risk, georisk events | [Caldara & Iacoviello GPR](https://www.matteoiacoviello.com/gpr.htm) | Free for research with attribution (Caldara & Iacoviello 2022, AER) |
| central bank rates, policy changes | [BIS policy rates](https://data.bis.org/topics/CBPOL) | Free use with attribution |
| commodities (annual) | [World Bank "Pink Sheet"](https://www.worldbank.org/en/research/commodity-markets) | CC BY 4.0 |
| GDP | [datasets/gdp](https://github.com/datasets/gdp) (World Bank) | CC BY 4.0 |
| population, inflation, oil, gold, VIX, S&P 500, 10y yield | [github.com/datasets](https://github.com/datasets) | ODC-PDDL-1.0 |
| companies | Wikipedia (Forbes Global 2000, largest by revenue) | CC BY-SA 4.0 |
| political events | Curated seed + English Wikipedia year pages | CC0 compilation; Wikipedia text CC BY-SA 4.0 |

**Code is MIT. Data is not** — see `LICENSE`. In particular the Wikipedia-derived company
and event data is CC BY-SA (share-alike), and GPR requires academic attribution.

Where an official bulk file exists it is used instead of scraping. BIS, FRED and World Bank
files are authoritative, carry explicit units, and stay correct when revised.

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

**GPR modern and historical are different series.** `GPR` starts in 1985; `GPRH` (labelled
"(historical)") runs from 1900. They are not spliced, because the underlying newspaper set
differs. The dataset reaches 1900 only via the historical variants — the UI selects both by
default so the span is visible rather than looking like the data begins in 1985.

**`market_drivers` is US-centric.** FRED's free coverage of non-US macro is thin, so the
rates, credit, housing and activity channels are US. The `fx` channel is global by
construction, and `central_bank_rates` covers 49 countries.

**Positioning is as of Tuesday but published Friday.** `cftc_positioning` carries the
Tuesday date, because that is what the CFTC reports. Any analysis that joins it to a Tuesday
price is using information nobody had until Friday — shift it forward three days first. This
is the single easiest way to manufacture a fake edge out of this dataset.

**One contract per commodity in `cftc_positioning`.** A commodity spans full-size, mini and
multiple-exchange contracts with different multipliers; summing them is meaningless, so the
most-reported contract is kept and named in the `contract` column. Net positioning is
expressed as a share of open interest rather than raw contracts, because raw counts grow with
the market and a 1995 net long is not comparable to a 2025 one.

**The WUI is republished at a dated URL each year, and the widely-linked mirror is stale.**
The copy on policyuncertainty.com ends in 2019Q3 while the live file runs to 2024Q4, and
nothing in the stale file says so. `uncertainty.py` fetches every candidate and keeps whichever
reaches furthest, then asserts the result extends past 2023 so a silent fallback fails the
build.

**`uncertainty_epu` country files each have their own layout.** The publisher ships one
workbook per country with no common schema — some use Year/Month columns, some a `Date`
column, some leave it unnamed, Chile uses `1993m1` strings, and Spain and Chile put a citation
sentence where the header should be. The parser tries every sheet and header row and ranks the
results by quality rather than row count, because pushing the header down yields *more* rows
by melting the month column in as data. Getting this wrong is silent: an integer date column
parses "successfully" as nanoseconds since epoch and lands every row on 1970-01-01.

**`crypto_daily` is one exchange's tape,** not a volume-weighted composite, and 2012–2013
prints are thin and noisy. Coinbase was tried first and its public candle endpoint ignores the
start/end parameters, returning only the last 300 days.

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
