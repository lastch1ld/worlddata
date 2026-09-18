"""NY Fed Global Supply Chain Pressure Index: the physical world, as one number.

Everything else in this repo reaches prices through finance - rates, positioning, sentiment.
This reaches them through ships. GSCPI folds transport costs (Baltic Dry, Harpex, air
freight) and PMI delivery-time and backlog subcomponents from the euro area, China, Japan,
South Korea, the UK and the US into a single standard-deviations-from-average measure.

It is the cleanest free answer to "was this inflation about money or about containers",
which is otherwise a matter of opinion. Zero means normal; the 2021 peak is above 4.

Monthly, 1997 onwards, revised when the inputs revise.

Licence: free to use with attribution to the Federal Reserve Bank of New York.
https://www.newyorkfed.org/research/policy/gscpi
"""
import io

import pandas as pd

from .common import fetch, write

URL = ("https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/"
       "gscpi_data.xlsx")


def collect():
    # The sheet has the NY Fed letterhead in the first rows, so the header lands on row 0
    # with the data starting a few rows down; coercing and dropping handles it without a
    # hard-coded skiprows that breaks on the next re-export.
    d = pd.read_excel(io.BytesIO(fetch(URL)), sheet_name="GSCPI Monthly Data")
    dcol = next((c for c in d.columns if str(c).strip().lower() == "date"), d.columns[0])
    vcol = next((c for c in d.columns if str(c).strip().upper() == "GSCPI"), d.columns[1])
    out = pd.DataFrame({
        "date": pd.to_datetime(d[dcol], errors="coerce"),
        "value": pd.to_numeric(d[vcol], errors="coerce"),
    }).dropna()
    out["series"] = "Global supply chain pressure"
    out["unit"] = "standard deviations from average"

    assert len(out) > 200, f"only {len(out)} GSCPI observations - file layout may have changed"
    # The index is normalised to mean zero. A version that is not centred means the wrong
    # column was picked (the sheet also carries raw subcomponents).
    assert abs(out["value"].mean()) < 0.5, f"GSCPI not centred (mean {out['value'].mean():.2f})"
    assert out["value"].max() > 2, "no 2021 spike - wrong column?"

    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return write("supply_chain_pressure", out[["date", "series", "value", "unit"]],
                 source=URL,
                 licence="Free use with attribution to the Federal Reserve Bank of New York.",
                 note=("Monthly, 1997 onwards. Transport costs plus PMI delivery-time and "
                       "backlog subcomponents across six economies, expressed as standard "
                       "deviations from average. Zero is normal. The 2021 peak above 4 is "
                       "the container crisis. Revised when its inputs revise."))


if __name__ == "__main__":
    collect()
