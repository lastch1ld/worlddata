"""Central bank policy rates, from the BIS.

The BIS publishes the official policy rate for ~40 central banks back to 1946 in one bulk
file. This is the authoritative source - preferred over scraping individual central bank
sites, which disagree on definitions (target vs effective vs corridor midpoint).

Licence: BIS statistics are free to use with attribution. See
https://www.bis.org/terms_conditions.htm
"""
import io
import zipfile

import pandas as pd

from .common import fetch, write

URL = "https://data.bis.org/static/bulk/WS_CBPOL_csv_flat.zip"


def collect():
    z = zipfile.ZipFile(io.BytesIO(fetch(URL)))
    with z.open(z.namelist()[0]) as f:
        raw = pd.read_csv(f, low_memory=False)
    # BIS ships "CODE:Label" headers; keep the code half
    raw.columns = [c.split(":")[0] for c in raw.columns]

    # FREQ values are also "CODE: Label" - match on the code, not the whole string,
    # or you silently select nothing and ship an empty dataset.
    freq = raw["FREQ"].astype(str).str.split(":").str[0].str.strip()
    monthly = raw[freq == "M"].copy()
    assert len(monthly), "no monthly rows - BIS changed their FREQ encoding"

    monthly["country"] = monthly["REF_AREA"].astype(str).str.split(":").str[1].str.strip()
    monthly["iso2"] = monthly["REF_AREA"].astype(str).str.split(":").str[0].str.strip()
    monthly["value"] = pd.to_numeric(monthly["OBS_VALUE"], errors="coerce")
    monthly["date"] = pd.to_datetime(monthly["TIME_PERIOD"], errors="coerce")

    out = (monthly.dropna(subset=["value", "date"])
           .rename(columns={"country": "series"})[["date", "series", "iso2", "value"]]
           .sort_values(["series", "date"]))
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out["unit"] = "percent per annum"
    return write("central_bank_rates", out,
                 source=URL,
                 licence="BIS - free use with attribution",
                 note="Official policy rate, monthly. One row per country per month.")


if __name__ == "__main__":
    collect()
