"""A catalogue of open datasets we do NOT vendor, with a one-call fetcher for each.

WHY NOT JUST COPY EVERYTHING IN
"Most comprehensive dataset on GitHub" sounds like it means copying as much data as
possible into this repo. It does not, for four reasons that bite in that order:

  1. LICENCES. Much good open data is share-alike (CC BY-SA, ODbL). Copying it in means
     this repo inherits those terms for everyone downstream. Our own collectors are
     permissive; mixing silently takes that away from people who import us.
  2. STALENESS. OWID updates daily. A copy in git is wrong within a week and looks
     authoritative while being wrong, which is worse than not having it.
  3. SIZE. Git stores every version of every file forever. A 200 MB CSV rebuilt weekly
     becomes tens of gigabytes of history that nobody can clone.
  4. DUPLICATION. These repos already exist on GitHub and are better maintained upstream
     than a copy here would be.

So: vendor what is small, permissive and slow-moving (see datahub.py). Register everything
else, and fetch it on demand. The registry is the comprehensive part - it is cheap to grow
to hundreds of entries, and each stays correct because it is read from source.

    from collectors.registry import catalogue, load
    catalogue()                     # everything we know about
    load("owid-energy")             # a DataFrame, fetched live
"""
import io
import json
from pathlib import Path

import pandas as pd

from .common import DATA, fetch

REGISTRY_FILE = Path(__file__).resolve().parent / "registry.json"

# Seed entries. Each is a real, checked URL to a machine-readable file - not a homepage.
# `vendored` marks the ones datahub.py already copies into data/.
SEED = [
    dict(key="owid-energy", title="Energy: production, consumption, mix, by country",
         publisher="Our World in Data", licence="CC-BY-4.0", format="csv",
         url="https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv",
         repo="owid/energy-data", topics=["energy", "country", "annual"], vendored=False),
    dict(key="owid-co2", title="CO2 and greenhouse gas emissions by country",
         publisher="Our World in Data", licence="CC-BY-4.0", format="csv",
         url="https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv",
         repo="owid/co2-data", topics=["climate", "country", "annual"], vendored=False),
    dict(key="owid-covid", title="COVID-19 cases, deaths, testing, vaccination",
         publisher="Our World in Data", licence="CC-BY-4.0", format="csv",
         url="https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv",
         repo="owid/covid-19-data", topics=["health", "country", "daily"], vendored=False),
    dict(key="sp500-constituents", title="S&P 500 constituents with sector and financials",
         publisher="datasets (Frictionless)", licence="ODC-PDDL-1.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
         repo="datasets/s-and-p-500-companies", topics=["equities", "reference"], vendored=False),
    dict(key="country-codes", title="ISO 3166 / currency / dialing codes crosswalk",
         publisher="datasets (Frictionless)", licence="ODC-PDDL-1.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/country-codes/main/data/country-codes.csv",
         repo="datasets/country-codes", topics=["reference"], vendored=False),
    dict(key="currency-codes", title="ISO 4217 currency codes",
         publisher="datasets (Frictionless)", licence="ODC-PDDL-1.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/currency-codes/main/data/codes-all.csv",
         repo="datasets/currency-codes", topics=["reference"], vendored=False),
    dict(key="gdp", title="GDP in current USD by country and year",
         publisher="World Bank via datasets", licence="CC-BY-4.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/gdp/main/data/gdp.csv",
         repo="datasets/gdp", topics=["macro", "country", "annual"], vendored=True),
    dict(key="population", title="Population by country and year",
         publisher="World Bank via datasets", licence="ODC-PDDL-1.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/population/main/data/population.csv",
         repo="datasets/population", topics=["macro", "country", "annual"], vendored=True),
    dict(key="inflation", title="Consumer price inflation by country and year",
         publisher="World Bank via datasets", licence="ODC-PDDL-1.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/inflation/main/data/inflation-consumer.csv",
         repo="datasets/inflation", topics=["macro", "country", "annual"], vendored=True),
    dict(key="oil-prices", title="Brent and WTI crude prices",
         publisher="US EIA via datasets", licence="ODC-PDDL-1.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/oil-prices/main/data/brent-daily.csv",
         repo="datasets/oil-prices", topics=["commodities", "daily"], vendored=True),
    dict(key="vix", title="CBOE Volatility Index, daily OHLC",
         publisher="CBOE via datasets", licence="ODC-PDDL-1.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv",
         repo="datasets/finance-vix", topics=["volatility", "daily"], vendored=True),
    dict(key="sp500-shiller", title="Shiller S&P 500 monthly with CAPE back to 1871",
         publisher="Robert Shiller via datasets", licence="ODC-PDDL-1.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/s-and-p-500/main/data/data.csv",
         repo="datasets/s-and-p-500", topics=["equities", "monthly"], vendored=True),
    dict(key="gold-prices", title="Gold price, monthly and annual",
         publisher="datasets (Frictionless)", licence="ODC-PDDL-1.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv",
         repo="datasets/gold-prices", topics=["commodities", "monthly"], vendored=True),
    dict(key="us-10y", title="US 10-year Treasury yield, monthly",
         publisher="datasets (Frictionless)", licence="odc-pddl", format="csv",
         url="https://raw.githubusercontent.com/datasets/bond-yields-us-10y/main/data/monthly.csv",
         repo="datasets/bond-yields-us-10y", topics=["rates", "monthly"], vendored=True),
    dict(key="geo-countries", title="Country polygons as GeoJSON",
         publisher="datasets (Frictionless)", licence="ODC-PDDL-1.0", format="geojson",
         url="https://raw.githubusercontent.com/datasets/geo-countries/main/data/countries.geojson",
         repo="datasets/geo-countries", topics=["geo", "reference"], vendored=False),
    dict(key="world-cities", title="Major world cities with coordinates",
         publisher="datasets (Frictionless)", licence="ODC-PDDL-1.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/world-cities/main/data/world-cities.csv",
         repo="datasets/world-cities", topics=["geo", "reference"], vendored=False),
    dict(key="airport-codes", title="Airports with IATA/ICAO codes and coordinates",
         publisher="datasets (Frictionless)", licence="ODC-PDDL-1.0", format="csv",
         url="https://raw.githubusercontent.com/datasets/airport-codes/main/data/airport-codes.csv",
         repo="datasets/airport-codes", topics=["geo", "transport", "reference"], vendored=False),
]


def catalogue(refresh=False):
    """The registry as a DataFrame. Written to data/registry.json so the UI can read it."""
    if refresh or not REGISTRY_FILE.exists():
        REGISTRY_FILE.write_text(json.dumps(SEED, indent=1), encoding="utf-8")
    entries = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    return pd.DataFrame(entries)


def load(key, **read_kw):
    """Fetch one registered dataset live and return it as a DataFrame."""
    entries = {e["key"]: e for e in json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))} \
        if REGISTRY_FILE.exists() else {e["key"]: e for e in SEED}
    if key not in entries:
        raise KeyError(f"{key} not in registry. Known: {sorted(entries)}")
    e = entries[key]
    if e["format"] == "csv":
        return pd.read_csv(io.StringIO(fetch(e["url"], binary=False)), **read_kw)
    if e["format"] == "geojson":
        return json.loads(fetch(e["url"], binary=False))
    raise ValueError(f"unhandled format {e['format']}")


def verify(keys=None, timeout_each=40):
    """HEAD/GET every registered URL so a dead link fails here, not for a user.

    A registry of broken links is worse than no registry, so this is part of the build.
    """
    import requests
    from .common import UA
    entries = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    bad = []
    for e in entries:
        if keys and e["key"] not in keys:
            continue
        try:
            r = requests.get(e["url"], headers=UA, timeout=timeout_each, stream=True)
            ok = r.status_code == 200
            size = int(r.headers.get("content-length") or 0)
            r.close()
        except Exception as ex:
            ok, size = False, 0
            r = type("x", (), {"status_code": type(ex).__name__})()
        print(f"  {'ok ' if ok else 'DEAD'} {e['key']:<22}{str(r.status_code):<10}"
              f"{size / 1024:>9,.0f} KB  {e['licence']}")
        if not ok:
            bad.append(e["key"])
    assert not bad, f"dead registry links: {bad}"
    return len(entries)


def collect():
    cat = catalogue(refresh=True)
    DATA.mkdir(exist_ok=True)
    (DATA / "registry.json").write_text(
        json.dumps(json.loads(REGISTRY_FILE.read_text(encoding="utf-8")), indent=1),
        encoding="utf-8")
    n_v = int(cat["vendored"].sum())
    print(f"  registry               {len(cat):>8} entries  "
          f"({n_v} vendored, {len(cat) - n_v} fetch-on-demand)")
    return cat


if __name__ == "__main__":
    collect()
    verify()
