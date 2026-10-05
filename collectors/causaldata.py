"""The causaldata teaching datasets that fit our tidy shape.

`causaldata` (Huntington-Klein, MIT) bundles 34 datasets from causal-inference textbooks. Most
are cross-sectional microdata and stay in the registry (`registry.load("causaldata-<name>")`).
These four have a real time axis and a stable entity key, so they take [date, series, value].

Kept in the registry on purpose, although they are time-indexed:
  avocado       Kaggle dataset; the package does not state its licence
  google_stock  returns downloaded through tidyquant (market data from Yahoo Finance)
  castle        states appear only as a numeric `sid`; naming them would be guesswork
Third-party terms we cannot verify are exactly what the registry exists to avoid copying.
"""
import pandas as pd

from .common import write
from .registry import catalogue, load

MIT = "MIT (causaldata package); data per original source"
SOURCE_REPO = "github.com/NickCH-K/causaldata"

# Units are the package documentation's own wording; where it gives none we say "rate".
GAPMINDER = {"lifeExp": "years", "pop": "people", "gdpPercap": "USD per person, inflation-adjusted"}
TEXAS = {"bmprison": "persons", "wmprison": "persons", "alcohol": "per capita",
         "income": "median income", "ur": "rate", "poverty": "rate",
         "black": "percent of population", "perc1519": "percent of population",
         "aidscapita": "AIDS deaths per 100,000"}


def _panel(df, entity, units):
    """Entity x year x variable -> one row per (series, date) with series 'entity: variable'."""
    out = df.melt(id_vars=[entity, "year"], value_vars=list(units), var_name="var")
    out["series"] = out[entity].astype(str) + ": " + out["var"]
    out["unit"] = out["var"].map(units)
    out["date"] = out["year"].astype(int).astype(str) + "-12-31"
    return out


def _organ_donations(df):
    q = df["Quarter"].str.extract(r"^Q(\d)(\d{4})$").astype(int)   # "Q42010" -> 4, 2010
    out = pd.DataFrame({"series": df["State"], "value": df["Rate"], "unit": "rate"})
    out["date"] = (pd.to_datetime(q[1].astype(str) + "-" + (q[0] * 3).astype(str) + "-01")
                   + pd.offsets.MonthEnd(0)).dt.strftime("%Y-%m-%d")
    return out


def _snow(df):
    out = pd.DataFrame({"series": df["supplier"], "value": df["deathrate"],
                        "unit": "deaths per 10,000 (1851 population)",
                        "treatment": df["treatment"]})
    out["date"] = df["year"].astype(str) + "-12-31"
    return out


# name -> (registry key, reshape, licence, note)
SPEC = {
    "causaldata_gapminder": (
        "gapminder", lambda d: _panel(d, "country", GAPMINDER), "CC0-1.0 (gapminder R package)",
        "Life expectancy, population and GDP per capita for 142 countries, every five years "
        "1952-2007. Gapminder via the gapminder R package; used in The Effect, fixed-effects chapter."),
    "causaldata_texas": (
        "texas", lambda d: _panel(d, "state", TEXAS), MIT,
        "State-year panel 1985-2000: prison populations by race and state covariates. "
        "Cunningham & Kang (2019); the Mixtape's synthetic-control example, where Texas is treated."),
    "causaldata_organ_donations": (
        "organ_donations", _organ_donations, MIT,
        "Quarterly organ-donation rate for 27 states around California's 2011 policy change "
        "(California is the treated group). Kessler & Roth (2014), NBER w20378; difference-in-differences."),
    "causaldata_snow": (
        "snow", _snow, MIT,
        "John Snow's cholera death rates by water supplier, 1849 and 1854; the `treatment` column "
        "is the supplier's water status. Snow (1855), Coleman (2019); difference-in-differences."),
}


def _tidy(key, reshape):
    df = load("causaldata-" + key.replace("_", "-"))
    for c in df.select_dtypes("float32"):   # via the shortest repr, or 20.6 becomes 20.600000381
        df[c] = df[c].astype(str).astype("float64")
    out = reshape(df)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["value"])
    dup = out.duplicated(["date", "series"]).sum()
    assert not dup, f"{key}: {dup} duplicate (date, series) rows"
    out["source_repo"] = SOURCE_REPO
    cols = ["date", "series", "value", "unit", "source_repo"] + (
        ["treatment"] if "treatment" in out else [])
    return out[cols].sort_values(["series", "date"]).reset_index(drop=True)


def collect(only=None):
    urls = catalogue().set_index("key")["url"]
    metas = []
    for name, (key, reshape, licence, note) in SPEC.items():
        if only and name not in only:
            continue
        try:
            df = _tidy(key, reshape)
        except Exception as e:
            print(f"  ! {name}: {type(e).__name__} {str(e)[:60]}")
            continue
        metas.append(write(name, df, source=urls["causaldata-" + key.replace("_", "-")],
                           licence=licence, note=note))
    return metas


if __name__ == "__main__":
    collect()
