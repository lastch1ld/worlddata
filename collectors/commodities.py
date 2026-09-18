"""Annual commodity prices from the World Bank "Pink Sheet".

Gold, crude oil (Brent / WTI / Dubai / average) and natural gas (US / Europe / Japan LNG),
annual, back to 1960, in nominal USD. The World Bank publishes this monthly as the
authoritative free reference series - better than scraping a price site, and it carries
explicit units, which most scraped price data does not.

Licence: World Bank Open Data, CC BY 4.0 - https://datacatalog.worldbank.org/public-licenses
"""
import pandas as pd

from .common import read_excel, write

URL = ("https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/"
       "related/CMO-Historical-Data-Annual.xlsx")

# What we surface by default. The sheet carries ~70 commodities; these are the ones asked
# for, plus the close substitutes that make the oil and gas lines interpretable.
WANTED = {
    "Gold": "gold",
    "Crude oil, average": "oil_crude_average",
    "Crude oil, Brent": "oil_brent",
    "Crude oil, WTI": "oil_wti",
    "Crude oil, Dubai": "oil_dubai",
    "Natural gas, US": "gas_us",
    "Natural gas, Europe": "gas_europe",
    "Liquefied natural gas, Japan": "gas_lng_japan",
    "Natural gas index": "gas_index",
    "Silver": "silver",
    "Copper": "copper",
}


def collect(all_commodities=False):
    raw = read_excel(URL, sheet_name="Annual Prices (Nominal)", header=None)
    # row 6 = commodity names, row 7 = units, data from row 8; column 0 = year
    names = raw.iloc[6].tolist()
    units = raw.iloc[7].tolist()
    body = raw.iloc[8:].copy()

    rows = []
    for col in range(1, raw.shape[1]):
        name = str(names[col]).strip()
        if name in ("nan", ""):
            continue
        key = WANTED.get(name)
        if key is None and not all_commodities:
            continue
        key = key or name.lower().replace(",", "").replace(" ", "_")
        unit = str(units[col]).strip().strip("()")
        for _, r in body.iterrows():
            year = str(r.iloc[0]).strip()
            if not year[:4].isdigit():
                continue
            val = pd.to_numeric(r.iloc[col], errors="coerce")
            if pd.isna(val):
                continue
            rows.append({"date": f"{year[:4]}-12-31", "year": int(year[:4]),
                         "series": key, "label": name, "value": float(val), "unit": unit})
    out = pd.DataFrame(rows).sort_values(["series", "year"])
    assert out["series"].nunique() >= 5, f"only found {out['series'].nunique()} series"
    return write("commodities_annual", out,
                 source=URL,
                 licence="World Bank Open Data, CC BY 4.0",
                 note="Annual nominal USD prices. Units vary by commodity - see the unit column.")


if __name__ == "__main__":
    collect()
