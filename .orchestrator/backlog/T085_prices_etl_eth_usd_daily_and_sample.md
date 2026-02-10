---
task_id: T085
title: "Prices ETL: ingest daily ETH/USD series + golden sample"
workstream: W1
role: Worker
priority: medium
dependencies:
  - "T096"
parallel_ok: true
allowed_paths:
  - "src/etl/prices_fetch.py"
  - "data/raw/prices/"
  - "data/raw_manifest/prices_"
  - "data/processed/prices/"
  - "data/processed_manifest/prices_"
  - "data/samples/prices/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/analysis/"
  - "src/validation/"
outputs:
  - "src/etl/prices_fetch.py"
  - "data/raw/prices/YYYY-MM-DD/..."
  - "data/raw_manifest/prices_YYYY-MM-DD.json"
  - "data/processed/prices/prices_daily.parquet"
  - "data/processed_manifest/prices_daily_YYYY-MM-DD.json"
  - "data/samples/prices/prices_daily_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Need API credentials"
  - "Source instability / breaking changes"
---

# Task T085 — Prices ETL: ingest daily ETH/USD series + golden sample

## Context

USD series are explicitly secondary in `docs/protocol.md`, but are useful for interpretation and certain counterfactual presentations. This task creates a reproducible daily ETH/USD series with raw snapshots and a committed tiny sample.

## Inputs

- Primary price source (example): CoinGecko (or a stable alternative)
- Optional secondary source for tolerance checks (document choice in the task)

## Outputs

- ETL code: `src/etl/prices_fetch.py`
- Raw snapshots (append-only): `data/raw/prices/<YYYY-MM-DD>/...`
- Raw manifest (tracked): `data/raw_manifest/prices_<YYYY-MM-DD>.json`
- Normalized daily price table (not committed): `data/processed/prices/prices_daily.parquet`
  - Include: `date_utc`, `eth_usd_close` (and other columns only if clearly defined).
- Processed manifest (tracked): `data/processed_manifest/prices_daily_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/prices/prices_daily_sample.csv`
  - Prefer the repo’s canonical sample window (see `data/samples/README.md`) so sample-mode joins align.

## Success Criteria

- [ ] Daily series covers the protocol window (2022-01-01 → present, with documented endpoints)
- [ ] Raw manifest exists and is append-only
- [ ] Normalized table schema is asserted (required columns at minimum: `date_utc`, `eth_usd_close`; fail fast on missing/invalid columns)
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` and includes input manifests + output hashes
- [ ] Golden sample is committed and stable
- [ ] `make gate` passes

## Status
- State: done
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-01-30: Task created (Planner) to support secondary USD conversions and figures.


- 2026-02-10: Claimed by swarm runner; starting worker (branch: T085_prices_etl_eth_usd_daily_and_sample).


- 2026-02-10: Implemented `src/etl/prices_fetch.py` source routing for `coingecko|cryptocompare|yahoo`, with automatic fallback from CoinGecko to CryptoCompare on 401/403 when no API key is provided. Raw snapshots now include `source`, `request_url`, `fetched_at_utc`, and nested `payload` metadata.
- 2026-02-10: Generated ETH/USD daily series from 2022-01-01 through 2026-02-10 using CryptoCompare (`data/processed/prices/prices_daily.csv`, 1502 rows, required schema asserted in code).
- 2026-02-10: Wrote append-only provenance artifacts:
  - `data/raw_manifest/prices_2026-02-10.json` (input raw snapshot: `data/raw/prices/2026-02-10/cryptocompare/eth_usd_histoday.json`)
  - `data/raw_manifest/prices_yahoo_probe_2026-02-10.json` (captures the earlier Yahoo probe snapshot path under `data/raw/prices/2026-02-10/`)
  - `data/processed_manifest/prices_daily_2026-02-10.json` (input raw manifest + output hash for `data/processed/prices/prices_daily.csv`)
- 2026-02-10: Refreshed canonical sample output at `data/samples/prices/prices_daily_sample.csv` (2024-02-20..2024-04-30, deterministic).
- 2026-02-10: Gates run:
  - `GIT_DIR=/tmp/wt-T085-git/.git GIT_WORK_TREE=/tmp/swarm-worktrees/wt-T085 GATE_BASE_REF=main make gate` (pass)
  - `make test` (pass, 41 tests)
- 2026-02-10: Limitation: task frontmatter lists a `.parquet` processed output path, but repo ETL currently uses stdlib-only CSV outputs (no parquet dependency/tooling present in environment).


- 2026-02-10: Judge: gates ok; ownership ok. Review log: /tmp/swarm-worktrees/wt-T085/data/tmp/swarm_logs/T085_20260210T003845Z_judge_review.txt
