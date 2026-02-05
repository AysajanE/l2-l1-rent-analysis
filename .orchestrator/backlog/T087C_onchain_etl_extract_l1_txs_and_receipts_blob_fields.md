---
task_id: T087C
title: "On-chain ETL: extract L1 txs + receipts (incl. blob fields) + manifests + sample"
workstream: W2
role: Worker
priority: high
dependencies:
  - "T096"
  - "T087A"
parallel_ok: false
allowed_paths:
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
  - "src/etl/l1_extract_txs_receipts.py"
  - "data/raw/l1/YYYY-MM-DD/txs/..."
  - "data/raw/l1/YYYY-MM-DD/receipts/..."
  - "data/raw_manifest/l1_txs_receipts_YYYY-MM-DD.json"
  - "data/processed/l1/l1_txs.parquet"
  - "data/processed/l1/l1_receipts.parquet"
  - "data/processed_manifest/l1_txs_receipts_YYYY-MM-DD.json"
  - "data/samples/l1/l1_txs_receipts_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Need RPC credentials"
  - "Receipt/tx blob fields unavailable post-Dencun (cannot compute burn_blob_wei)"
  - "Extraction requires protocol/contract reinterpretation"
---

# Task T087C — On-chain ETL: extract L1 txs + receipts (incl. blob fields) + manifests + sample

## Context

This task extracts the transaction + receipt tables needed for fee decomposition:
- execution-layer burn + tips (EIP‑1559)
- blob fee burn (EIP‑4844) for type‑3 transactions

It is intentionally scoped to txs+receipts only, with explicit join keys, and depends on T087A so the swarm fails fast if blob fields are unavailable.

## Inputs

- RPC endpoint via `ETH_RPC_URL`
- `docs/protocol.md` (read-only): fee component definitions and blob fee computation rules
- `scripts/make_raw_manifest.py`
- `scripts/make_processed_manifest.py` (T096)

## Outputs

- ETL code: `src/etl/l1_extract_txs_receipts.py`
- Raw snapshots (append-only; not committed):
  - `data/raw/l1/<YYYY-MM-DD>/txs/...`
  - `data/raw/l1/<YYYY-MM-DD>/receipts/...`
- Raw manifest (tracked): `data/raw_manifest/l1_txs_receipts_<YYYY-MM-DD>.json`
- Processed tables (not committed):
  - `data/processed/l1/l1_txs.parquet`
  - `data/processed/l1/l1_receipts.parquet`
  - Must include join keys: `tx_hash`, `block_number` (and `tx_index` if needed)
  - Must include (at minimum):
    - tx type (`tx_type`) and blob identification fields (e.g., `blobVersionedHashes` or equivalent)
    - receipt fields needed for fee computation: `gas_used`, `effective_gas_price_wei`, and blob fields when present (`blobGasUsed`, `blobGasPrice`)
- Processed manifest (tracked): `data/processed_manifest/l1_txs_receipts_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/l1/l1_txs_receipts_sample.csv`
  - Must include at least one post‑Dencun blob tx row if feasible.
  - Prefer a sample drawn from the canonical sample window (see `data/samples/README.md`), but keep extraction volume tiny; sample may be sparse within the window.

## Success Criteria

- [ ] Preflight passes: `make preflight-onchain`
- [ ] Raw snapshots are append-only and reproducible
- [ ] Raw manifest exists and validates via `make gate`
- [ ] Sample window includes at least one type‑3 (blob) tx **or** the task blocks with `@human` and a provider capability summary
- [ ] For blob txs in the sample, extracted fields are sufficient to compute `burn_blob_wei` deterministically (receipt preferred; payload/header fallback allowed per protocol)
- [ ] Tx/receipt table schemas are asserted (required join keys + fee component fields; fail fast on missing/invalid columns)
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` and includes input manifests + output hashes
- [ ] Sample is committed and stable
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-02-05

## Notes / Decisions

- 2026-02-04: Split out from the original monolithic T087 to isolate tx/receipt schema and blob-field availability issues.
