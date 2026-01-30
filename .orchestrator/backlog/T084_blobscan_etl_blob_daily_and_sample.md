---
task_id: T084
title: "Blobscan ETL: ingest blob daily aggregates + golden sample"
workstream: W1
role: Worker
priority: medium
dependencies: []
parallel_ok: true
allowed_paths:
  - "src/etl/blobscan_fetch.py"
  - "data/raw/blobscan/"
  - "data/raw_manifest/blobscan_"
  - "data/processed/blobscan/"
  - "data/processed_manifest/blobscan_"
  - "data/samples/blobscan/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/analysis/"
  - "src/validation/"
outputs:
  - "src/etl/blobscan_fetch.py"
  - "data/raw/blobscan/YYYY-MM-DD/..."
  - "data/raw_manifest/blobscan_YYYY-MM-DD.json"
  - "data/processed/blobscan/blobscan_daily.parquet"
  - "data/processed_manifest/blobscan_daily_YYYY-MM-DD.json"
  - "data/samples/blobscan/blobscan_daily_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Blobscan endpoints require auth and no public alternative is available"
  - "Source instability / breaking changes"
---

# Task T084 — Blobscan ETL: ingest blob daily aggregates + golden sample

## Context

Blob regime identification and validation require blob market time series (base fee per blob gas, blob gas used, tx counts). Blobscan can provide convenience aggregates and/or labeling hints.

This task snapshots Blobscan outputs (append-only), normalizes a daily aggregate table, and commits a small golden sample for deterministic tests.

## Inputs

- Blobscan API docs / endpoints (verify at runtime): `https://docs.blobscan.com/docs/api`
- `docs/protocol.md` (read-only): blob regime definition + validation tolerances

## Outputs

- ETL code: `src/etl/blobscan_fetch.py`
  - Must support `--run-date YYYY-MM-DD`.
  - Must snapshot raw responses to `data/raw/blobscan/<YYYY-MM-DD>/...` (append-only).
- Raw manifest (tracked): `data/raw_manifest/blobscan_<YYYY-MM-DD>.json`
- Normalized daily table (not committed): `data/processed/blobscan/blobscan_daily.parquet`
  - Include at minimum: `date_utc`, `blob_base_fee_gwei` (or explicit wei field), `blob_gas_used`, `blob_tx_count`.
- Processed manifest (tracked): `data/processed_manifest/blobscan_daily_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/blobscan/blobscan_daily_sample.csv`

## Success Criteria

- [ ] Raw snapshots are append-only and reproducible
- [ ] Manifests (raw + processed) exist and are consistent
- [ ] Golden sample is committed and stable
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-01-30

## Notes / Decisions

- 2026-01-30: Task created (Planner) to support blob regime identification and cross-checks.

