"""Daily crypto prices from Bitstamp - a control group with no central bank.

WHY THIS BELONGS IN A REPO ABOUT MONEY AND WORLD EVENTS: every other asset here sits on the
same plumbing. When the Fed moves, rates, credit, FX and equities all respond partly because
they share a discount rate and a banking system. Crypto shares the risk appetite but not the
plumbing - no policy rate, no earnings, no coupon, no lender of last resort. That makes it a
useful control: if an event moves both, the channel was probably sentiment or liquidity; if
it moves only the traditional side, the channel was probably policy.

WHY BITSTAMP: Coinbase's public candle endpoint ignores the start/end parameters and returns
only the last 300 days, and CoinGecko and CryptoCompare now want a key for history. Bitstamp
paginates properly from 2011 with no key. Probed, not assumed.

CAVEAT: this is one exchange's tape, not a volume-weighted composite. Early years are thin
and the 2011-2013 prints are noisy. Good enough for "what happened", wrong for microstructure.

Licence: Bitstamp public market data, free to use. Attribute Bitstamp.
"""
import json
import time
from datetime import datetime, timezone

import pandas as pd

from .common import fetch, write

API = "https://www.bitstamp.net/api/v2/ohlc/{pair}/?step=86400&limit=1000&start={start}"
PAIRS = {"btcusd": "Bitcoin (BTC/USD)", "ethusd": "Ethereum (ETH/USD)",
         "xrpusd": "XRP (XRP/USD)", "ltcusd": "Litecoin (LTC/USD)",
         "bchusd": "Bitcoin Cash (BCH/USD)"}
START = 1325376000        # 2012-01-01; Bitstamp's own history starts around here
DAY = 86400


def _pair(pair):
    """Walk forward in 1000-day pages until the exchange stops returning new candles.

    Pairs listed later (ETH in 2017, BCH in 2018) simply return empty pages until their
    listing date, so no per-pair start date is needed - the loop finds it.
    """
    rows, start, seen = [], START, set()
    while True:
        try:
            page = json.loads(fetch(API.format(pair=pair, start=start), binary=False))
        except Exception as e:
            return pair, None, type(e).__name__
        candles = page.get("data", {}).get("ohlc", [])
        fresh = [c for c in candles if int(c["timestamp"]) not in seen]
        for c in fresh:
            seen.add(int(c["timestamp"]))
        rows.extend(fresh)
        if not candles:
            # Empty page before the listing date: skip ahead rather than stopping, or ETH
            # and BCH would return nothing at all.
            start += 1000 * DAY
        else:
            start = max(int(c["timestamp"]) for c in candles) + DAY
        if start > time.time():
            break
    if len(rows) < 200:
        return pair, None, f"only {len(rows)} candles"

    d = pd.DataFrame(rows)
    out = pd.DataFrame({
        "date": pd.to_datetime(pd.to_numeric(d["timestamp"]), unit="s", utc=True)
                  .dt.tz_convert(timezone.utc).dt.strftime("%Y-%m-%d"),
        "series": PAIRS[pair],
        "value": pd.to_numeric(d["close"], errors="coerce"),
        "volume": pd.to_numeric(d["volume"], errors="coerce"),
        "unit": "USD per coin",
    }).dropna(subset=["value"])
    out = out[out["value"] > 0].drop_duplicates(subset=["date"]).sort_values("date")
    return pair, out, None


def collect():
    frames, dropped = [], []
    for pair in PAIRS:
        name, df, why = _pair(pair)
        (frames.append(df) if df is not None else dropped.append((name, why)))
    for name, why in dropped:
        print(f"  ! dropped {name}: {why}")
    assert len(frames) >= 3, f"only {len(frames)} crypto pairs usable"

    out = pd.concat(frames, ignore_index=True).sort_values(["series", "date"])
    btc = out[out["series"].str.startswith("Bitcoin (")]
    assert btc["date"].min() < "2014-01-01", f"BTC history starts {btc['date'].min()}"
    assert btc["value"].max() > 10_000, "BTC never above $10k - wrong column?"
    return write("crypto_daily", out,
                 source="https://www.bitstamp.net/api/v2/ohlc/",
                 licence="Bitstamp public market data, free to use. Attribute Bitstamp.",
                 note=("Daily close and volume for five pairs, 2012 onwards. Included as a "
                       "CONTROL: crypto shares risk appetite with other assets but not the "
                       "policy rate, the banking system or a lender of last resort, so an "
                       "event that moves both suggests a sentiment or liquidity channel "
                       "rather than a policy one. One exchange's tape, not a composite - "
                       "early years are thin."))


if __name__ == "__main__":
    collect()
