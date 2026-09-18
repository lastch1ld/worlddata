"""Datasets published as Frictionless data packages by github.com/datasets.

These are already clean, versioned CSVs with explicit licences, so there is nothing to
scrape: fetch the file, reshape to our tidy schema, record where it came from.

WHY VENDOR THESE AT ALL, RATHER THAN LINK
Copying someone else's data is usually the wrong move - it goes stale, it bloats the repo,
and share-alike terms propagate. These eight are the exception: all are ODC-PDDL (a public
domain dedication) except GDP which is CC-BY-4.0 (attribution only), and all eight together
are 2.4 MB. Small, permissive, and useful offline. Anything share-alike, large, or fast
moving belongs in the registry instead, fetched on demand.

Every row records `source_repo` so provenance survives into the CSV, not just the metadata.
"""
import io

import pandas as pd

from .common import fetch, write

RAW = "https://raw.githubusercontent.com/datasets/{repo}/{branch}/{path}"

# name -> how to fetch and reshape it.
#   kind "country_year"  : Country / Code / Year / Value  -> series = country
#   kind "date_value"    : one date column, one value column
#   kind "wide"          : one date column, several value columns -> series = column name
SPEC = {
    "gdp_by_country": dict(
        repo="gdp", path="data/gdp.csv", kind="country_year",
        cols=("Country Name", "Year", "Value"), unit="current USD",
        licence="CC-BY-4.0", note="World Bank GDP in current US dollars, by country and year."),
    "population_by_country": dict(
        repo="population", path="data/population.csv", kind="country_year",
        cols=("Country Name", "Year", "Value"), unit="people",
        licence="ODC-PDDL-1.0", note="World Bank total population, by country and year."),
    "inflation_by_country": dict(
        repo="inflation", path="data/inflation-consumer.csv", kind="country_year",
        cols=("Country", "Year", "Inflation"), unit="percent per year",
        licence="ODC-PDDL-1.0", note="World Bank consumer price inflation, by country and year."),
    "oil_brent_daily": dict(
        repo="oil-prices", path="data/brent-daily.csv", kind="date_value",
        cols=("Date", "Price"), series="brent", unit="USD per barrel",
        licence="ODC-PDDL-1.0", note="Brent crude spot price, daily, from US EIA."),
    "oil_wti_daily": dict(
        repo="oil-prices", path="data/wti-daily.csv", kind="date_value",
        cols=("Date", "Price"), series="wti", unit="USD per barrel",
        licence="ODC-PDDL-1.0", note="WTI crude spot price, daily, from US EIA."),
    "gold_monthly": dict(
        repo="gold-prices", path="data/monthly.csv", kind="date_value",
        cols=("Date", "Price"), series="gold", unit="USD per troy ounce",
        licence="ODC-PDDL-1.0", note="Gold price, monthly."),
    "vix_daily": dict(
        repo="finance-vix", path="data/vix-daily.csv", kind="date_value",
        cols=("DATE", "CLOSE"), series="vix_close", unit="index",
        licence="ODC-PDDL-1.0", note="CBOE Volatility Index, daily close."),
    "us_10y_yield_monthly": dict(
        repo="bond-yields-us-10y", path="data/monthly.csv", kind="date_value",
        cols=("Date", "Rate"), series="us_10y", unit="percent per annum",
        licence="odc-pddl", note="US 10-year Treasury yield, monthly."),
    "sp500_monthly": dict(
        repo="s-and-p-500", path="data/data.csv", kind="wide",
        date_col="Date", value_cols=("SP500", "Dividend", "Earnings",
                                     "Consumer Price Index", "Long Interest Rate",
                                     "Real Price", "Real Dividend", "Real Earnings", "PE10"),
        unit="mixed - see series", licence="ODC-PDDL-1.0",
        note="Shiller S&P 500 monthly series including CAPE (PE10). Units differ per series."),
}


def _load(repo, path):
    """Try main then master - the org is mid-migration and both exist."""
    last = None
    for branch in ("main", "master"):
        try:
            return pd.read_csv(io.StringIO(
                fetch(RAW.format(repo=repo, branch=branch, path=path), binary=False)))
        except Exception as e:
            last = e
    raise RuntimeError(f"could not fetch {repo}/{path}: {last}")


def _tidy(name, spec):
    df = _load(spec["repo"], spec["path"])
    kind = spec["kind"]

    if kind == "country_year":
        c_country, c_year, c_val = spec["cols"]
        out = df[[c_country, c_year, c_val]].copy()
        out.columns = ["series", "year", "value"]
        out["date"] = out["year"].astype(str).str.slice(0, 4) + "-12-31"
    elif kind == "date_value":
        c_date, c_val = spec["cols"]
        out = df[[c_date, c_val]].copy()
        out.columns = ["date", "value"]
        out["series"] = spec["series"]
    elif kind == "wide":
        keep = [c for c in spec["value_cols"] if c in df.columns]
        assert keep, f"{name}: none of the expected value columns are present"
        out = df.melt(id_vars=[spec["date_col"]], value_vars=keep,
                      var_name="series", value_name="value")
        out.columns = ["date", "series", "value"]
    else:
        raise ValueError(kind)

    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["value"])
    # Dates arrive as 1871-01, 2020-01-01 or a bare year depending on the file.
    parsed = pd.to_datetime(out["date"], errors="coerce", format="mixed")
    out = out[parsed.notna()].copy()
    out["date"] = parsed[parsed.notna()].dt.strftime("%Y-%m-%d")
    out["unit"] = spec["unit"]
    out["source_repo"] = f"github.com/datasets/{spec['repo']}"
    cols = ["date", "series", "value", "unit", "source_repo"]
    return out[cols].sort_values(["series", "date"]).reset_index(drop=True)


def collect(only=None):
    metas = []
    for name, spec in SPEC.items():
        if only and name not in only:
            continue
        try:
            df = _tidy(name, spec)
        except Exception as e:
            print(f"  ! {name}: {type(e).__name__} {str(e)[:60]}")
            continue
        metas.append(write(name, df,
                           source=f"https://github.com/datasets/{spec['repo']}",
                           licence=spec["licence"], note=spec["note"]))
    return metas


if __name__ == "__main__":
    collect()
