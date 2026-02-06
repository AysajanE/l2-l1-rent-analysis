---
task_id: T087B
title: "On-chain ETL: extract L1 block headers (incl. blob header fields) + manifests + sample"
workstream: W2
role: Worker
priority: high
dependencies:
  - "T096"
  - "T087A"
required_env:
  - "ETH_RPC_URL"
parallel_ok: false
allowed_paths:
  - "src/etl/l1_extract_blocks.py"
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
  - "src/etl/l1_extract_blocks.py"
  - "data/raw/l1/YYYY-MM-DD/blocks/..."
  - "data/raw_manifest/l1_blocks_YYYY-MM-DD.json"
  - "data/processed/l1/l1_blocks.parquet"
  - "data/processed_manifest/l1_blocks_YYYY-MM-DD.json"
  - "data/samples/l1/l1_blocks_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Need RPC credentials"
  - "Block header blob fields unavailable post-Dencun"
  - "Extraction requires protocol/contract reinterpretation"
---

# Task T087B — On-chain ETL: extract L1 block headers (incl. blob header fields) + manifests + sample

## Context

This task extracts the L1 block header table required for fee component computation and blob fee fallback computation. It is intentionally scoped to **blocks only** (no txs/receipts) to keep the interface small and debuggable.

This task must depend on T087A so we do not attempt a broader extraction unless the RPC endpoint is “blob-ready” by an explicit acceptance test.

## Inputs

- RPC endpoint via `ETH_RPC_URL`
- `docs/protocol.md` (read-only): integer-safe blob fee computation rules + Dencun boundary
- `scripts/make_raw_manifest.py`
- `scripts/make_processed_manifest.py` (T096)

## Outputs

- ETL code: `src/etl/l1_extract_blocks.py`
- Raw snapshots (append-only; not committed): `data/raw/l1/<YYYY-MM-DD>/blocks/...`
- Raw manifest (tracked): `data/raw_manifest/l1_blocks_<YYYY-MM-DD>.json`
- Processed table (not committed): `data/processed/l1/l1_blocks.parquet`
  - Must include (at minimum):
    - `block_number`, `block_hash`, `timestamp_utc`
    - `base_fee_per_gas_wei`, `gas_used`
    - post‑Dencun: `blob_gas_used`, `excess_blob_gas` (or equivalent RPC fields needed to compute blob base fee deterministically)
- Processed manifest (tracked): `data/processed_manifest/l1_blocks_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/l1/l1_blocks_sample.csv`

## Success Criteria

- [ ] Preflight passes: `make preflight-onchain`
- [ ] Raw snapshots are append-only and reproducible
- [ ] Raw manifest exists and validates via `make gate`
- [ ] Processed blocks table contains required blob header fields for post‑Dencun blocks (sufficient for base-fee-per-blob-gas fallback computation)
- [ ] Blocks table schema is asserted (required columns at minimum: `block_number`, `block_hash`, `timestamp_utc`, `base_fee_per_gas_wei`, `gas_used`, and post‑Dencun blob header fields; fail fast on missing/invalid columns)
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` and includes input manifests + output hashes
- [ ] Sample is committed and stable (tiny fixed window spanning pre‑ and post‑Dencun)
  - Prefer coverage aligned to the canonical sample window intent (see `data/samples/README.md`), but keep extraction volume tiny; sample may be sparse within the window.
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-02-05

## Notes / Decisions

- 2026-02-04: Split out from the original monolithic T087 to reduce risk and isolate blob-header-field issues early.
