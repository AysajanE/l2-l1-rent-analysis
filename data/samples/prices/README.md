# `data/samples/prices/` — ETH/USD endpoint notes + sample conventions

USD conversions are **secondary** in this repo (interpretation only). The canonical series are ETH-native.

## Recommended source policy (initial)

- Primary: CoinGecko daily ETH/USD candles (public endpoint; may require API key depending on plan).
- Secondary (tolerance check): CryptoCompare / Coinbase candles.

## Required normalized fields (target schema)

- `date_utc` (YYYY-MM-DD, UTC)
- `eth_usd_close` (USD per ETH)

Optional:
- `eth_usd_open`, `high`, `low`
- `source`

## Repro commands (expected once ETL exists)

```bash
python src/etl/prices_fetch.py --run-date YYYY-MM-DD
python scripts/make_raw_manifest.py prices data/raw/prices/YYYY-MM-DD --as-of YYYY-MM-DD -- \
  python src/etl/prices_fetch.py --run-date YYYY-MM-DD
```
