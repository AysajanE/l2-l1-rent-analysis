# Handoff H085 — Prices ETL ETH/USD daily + sample

## Summary (1–3 sentences)
Completed T085 by extending `src/etl/prices_fetch.py` to support multiple sources (`coingecko`, `cryptocompare`, `yahoo`) with automatic fallback from CoinGecko to CryptoCompare when CoinGecko rejects unauthenticated requests. Generated a full daily ETH/USD series for `2022-01-01` through `2026-02-10`, plus raw and processed manifests and a refreshed canonical sample. All required gates/tests passed.

## What changed / what exists now

- Files/paths:
  - `src/etl/prices_fetch.py`
  - `data/raw/prices/2026-02-10/cryptocompare/eth_usd_histoday.json`
  - `data/raw/prices/2026-02-10/yahoo_eth_usd_chart.json` (left as append-only snapshot artifact from earlier source probe)
  - `data/raw_manifest/prices_2026-02-10.json`
  - `data/raw_manifest/prices_yahoo_probe_2026-02-10.json`
  - `data/processed/prices/prices_daily.csv`
  - `data/processed_manifest/prices_daily_2026-02-10.json`
  - `data/samples/prices/prices_daily_sample.csv`
- Outputs produced:
  - Normalized ETH/USD daily file with required columns (`date_utc`, `eth_usd_close`) and full window coverage (`1502` rows).
  - Raw + processed provenance manifests with hashes and reproducible commands.

## How to reproduce / verify

- Commands:
  - `python src/etl/prices_fetch.py --sample --overwrite`
  - `python src/etl/prices_fetch.py --run-date 2026-02-10 --source cryptocompare --write-raw --raw-out data/raw/prices/2026-02-10/cryptocompare/eth_usd_histoday.json --overwrite`
  - `python src/etl/prices_fetch.py --from-snapshot data/raw/prices/2026-02-10/cryptocompare/eth_usd_histoday.json --source cryptocompare --out data/processed/prices/prices_daily.csv --start-date 2022-01-01 --end-date 2026-02-10 --overwrite`
  - `python scripts/make_raw_manifest.py prices data/raw/prices/2026-02-10/cryptocompare --as-of 2026-02-10 -- python src/etl/prices_fetch.py --run-date 2026-02-10 --source cryptocompare --write-raw --raw-out data/raw/prices/2026-02-10/cryptocompare/eth_usd_histoday.json --overwrite`
  - `python scripts/make_processed_manifest.py prices_daily --as-of 2026-02-10 --inputs data/raw_manifest/prices_2026-02-10.json --outputs data/processed/prices/prices_daily.csv -- python src/etl/prices_fetch.py --from-snapshot data/raw/prices/2026-02-10/cryptocompare/eth_usd_histoday.json --source cryptocompare --out data/processed/prices/prices_daily.csv --start-date 2022-01-01 --end-date 2026-02-10 --overwrite`
  - `GIT_DIR=/tmp/wt-T085-git/.git GIT_WORK_TREE=/tmp/swarm-worktrees/wt-T085 GATE_BASE_REF=main make gate`
  - `make test`
- Expected results:
  - Snapshot/build commands print summary JSON with first/last dates and row count.
  - `make gate` passes all checks.
  - `make test` passes (`Ran 41 tests`).

## Assumptions / risks

- CoinGecko unauthenticated access currently returns `401` in this environment; task uses CryptoCompare as stable alternative per task input allowance.
- Processed output remains CSV (`data/processed/prices/prices_daily.csv`) because repo is stdlib-only with no parquet tooling/dependency declared.
- Quality gate command uses a local temporary git metadata repo due inaccessible worktree `.git` pointer path in sandbox.

## Open questions / next steps

- If strict `.parquet` output is required for downstream consumers, add and lock an explicit parquet dependency/tooling path in a dedicated task before switching output format.
