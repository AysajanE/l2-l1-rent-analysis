---
task_id: T087
title: "On-chain ETL: extract L1 blocks/txs/receipts (blob-ready) + manifests + sample"
workstream: W2
role: Worker
priority: high
dependencies: []
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

# Task T087 — On-chain ETL: extract L1 blocks/txs/receipts (blob-ready) + manifests + sample

## Context

The protocol prioritizes **on-chain computed** rent paid for `RentPaid_{i,t}`. To compute rollup-attributed rent and decompositions, we need a reproducible raw extraction of Ethereum L1 data that includes:
- block headers (including post-Dencun blob header fields),
- transactions (including type-3 blob txs),
- receipts (gas used, status, logs as needed).

This task builds the raw extraction layer and produces a small committed sample so downstream logic can be tested deterministically without a full backfill.

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
- [ ] Post-Dencun extracted data includes enough fields to compute blob base fee and blob fee burn
- [ ] Sample is committed and stable
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-01-30

## Notes / Decisions

- 2026-01-30: Task created (Planner) as the raw foundation for on-chain rent computation.

