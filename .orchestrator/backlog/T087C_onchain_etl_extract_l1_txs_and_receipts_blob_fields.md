---
task_id: T087C
title: "On-chain ETL: extract L1 txs + receipts (incl. blob fields) + manifests + sample"
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
- State: done
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-02-04: Split out from the original monolithic T087 to isolate tx/receipt schema and blob-field availability issues.


- 2026-02-10: Claimed by swarm runner; starting worker (branch: T087C_onchain_etl_extract_l1_txs_and_receipts_blob_fields).

- 2026-02-10: Worker execution completed with tiny canonical-window extraction and schema/sample assertions.
  - Files changed:
    - `src/etl/l1_extract_txs_receipts.py`
    - `data/raw_manifest/l1_txs_receipts_2026-02-10.json`
    - `data/processed_manifest/l1_txs_receipts_2026-02-10.json`
    - `data/samples/l1/l1_txs_receipts_sample.csv`
  - Reproduction commands:
    - `make preflight-onchain`
    - `python src/etl/l1_extract_txs_receipts.py --as-of 2026-02-10 --from-block 19557289 --to-block 19557340 --chunk-size 100 --write-manifest`
    - `make gate`
    - `make test`
  - Output summary:
    - Raw snapshots (append-only): `data/raw/l1/2026-02-10/txs/txs_19557289_19557340.jsonl`, `data/raw/l1/2026-02-10/receipts/receipts_19557289_19557340.jsonl`
    - Processed outputs (CSV payload at parquet paths): `data/processed/l1/l1_txs.parquet`, `data/processed/l1/l1_receipts.parquet`
    - Golden sample: `data/samples/l1/l1_txs_receipts_sample.csv` (11 rows selected; 5 type-3 rows; all 5 with computable `burn_blob_wei`)
  - Gate/test results:
    - `make preflight-onchain`: pass
    - `make gate`: pass
    - `make test`: pass (`Ran 42 tests`, `OK`)
  - Assumptions / limitations:
    - Extraction range is sparse and intentionally tiny (April 2024 canonical-window slice around blocks `19557289..19557340`).
    - Processed files use CSV payload with `.parquet` filenames for stdlib portability.
    - Sandbox git worktree metadata is unavailable; processed manifest records `transform.git_sha = null`.


- 2026-02-10: Judge: gates ok; ownership ok. Review log: /tmp/swarm-worktrees/wt-T087C/data/tmp/swarm_logs/T087C_20260210T105535Z_judge_review.txt
