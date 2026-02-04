---
task_id: T087
title: "DEPRECATED: monolithic L1 extraction task (superseded by T087A/B/C)"
workstream: W2
role: Worker
priority: high
dependencies:
  - "T096"
  - "T087A"
  - "T087B"
  - "T087C"
parallel_ok: false
allowed_paths:
  - "src/etl/rpc_client.py"
  - "src/etl/l1_extract_blocks.py"
  - "src/etl/l1_extract_txs_receipts.py"
  - "data/raw/l1/"
  - "data/raw_manifest/l1_"
  - "data/processed/l1/"
  - "data/processed_manifest/l1_"
  - "data/samples/l1/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/analysis/"
  - "src/validation/"
outputs:
  - "src/etl/rpc_client.py"
  - "src/etl/l1_extract_blocks.py"
  - "src/etl/l1_extract_txs_receipts.py"
  - "data/raw/l1/YYYY-MM-DD/..."
  - "data/raw_manifest/l1_YYYY-MM-DD.json"
  - "data/processed/l1/l1_blocks.parquet"
  - "data/processed/l1/l1_txs.parquet"
  - "data/processed/l1/l1_receipts.parquet"
  - "data/processed_manifest/l1_extract_YYYY-MM-DD.json"
  - "data/samples/l1/l1_extract_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Need RPC credentials"
  - "RPC performance insufficient for the required window"
- "Blob fields unavailable post-Dencun"
---

# Task T087 — DEPRECATED: monolithic L1 extraction task (superseded by T087A/B/C)

## Context

This task has been superseded by a safer split that adds an explicit “blob-ready” acceptance test and isolates extraction surfaces:

- **T087A**: RPC capability probe (type‑3 tx + blob field availability + computable `burn_blob_wei`)
- **T087B**: block header extractor (incl. blob header fields)
- **T087C**: tx+receipt extractor (incl. blob fields + join keys)

Workers should implement and run **T087A/B/C** instead of this monolithic task. This file remains to preserve historical references to `T087` and prevent ID drift in downstream discussions.

## Inputs

- Ethereum mainnet RPC endpoint (must be configured at runtime; do not commit secrets)
- `docs/protocol.md` (read-only): Dencun boundary and blob-field expectations
- `scripts/make_raw_manifest.py` (use for manifest generation)

## Outputs

- ETL code:
  - `src/etl/rpc_client.py` (shared RPC helper; retries/backoff; minimal dependencies)
  - `src/etl/l1_extract_blocks.py`
  - `src/etl/l1_extract_txs_receipts.py`
- Raw snapshots (append-only; not committed): `data/raw/l1/<YYYY-MM-DD>/...`
- Raw manifest (tracked): `data/raw_manifest/l1_<YYYY-MM-DD>.json`
- Normalized raw tables (not committed):
  - `data/processed/l1/l1_blocks.parquet`
  - `data/processed/l1/l1_txs.parquet`
  - `data/processed/l1/l1_receipts.parquet`
- Processed manifest (tracked): `data/processed_manifest/l1_extract_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/l1/l1_extract_sample.csv`
  - Must be small and sufficient to exercise:
    - pre- and post-Dencun blocks,
    - at least one blob tx if feasible.

## Success Criteria

- [ ] Extraction is reproducible (raw snapshots + manifests + deterministic transforms)
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` and includes input manifests + output hashes
- [ ] Post-Dencun extracted data includes enough fields to compute blob base fee and blob fee burn
- [ ] Sample is committed and stable
- [ ] `make gate` passes

## Status

- State: blocked
- Last updated: 2026-02-04

## Notes / Decisions

- 2026-01-30: Task created (Planner) as the raw foundation for on-chain rent computation.
- 2026-02-04: Deprecated and split into T087A/T087B/T087C with an explicit blob-field acceptance test (probe) before any backfill.
