# Handoff H114 — Split T087 into probe + blocks + txs/receipts (blob-ready acceptance)

## Summary (1–3 sentences)

Split the monolithic on-chain extraction task (T087) into three smaller W2 tasks: an RPC blob-field capability probe (T087A), a blocks header extractor (T087B), and a tx+receipt extractor (T087C). Updated dependency parsing to support `T###A`-style task IDs so the swarm and dependency gates work with the split.

## What changed / what exists now

- Files/paths:
  - Added: `.orchestrator/backlog/T087A_onchain_rpc_capability_probe_blob_fields.md`
  - Added: `.orchestrator/backlog/T087B_onchain_etl_extract_l1_block_headers_blob_fields.md`
  - Added: `.orchestrator/backlog/T087C_onchain_etl_extract_l1_txs_and_receipts_blob_fields.md`
  - Updated: `.orchestrator/backlog/T087_onchain_etl_l1_raw_extract_headers_txs_receipts.md` (marked `State: blocked`, deprecated)
  - Updated: `.orchestrator/backlog/T088_onchain_compute_rollup_daily_costs_and_decomposition.md` (depends on T087B/T087C instead of T087)
  - Updated: `scripts/quality_gates.py` (dependency ID validation allows `T\\d{3}[A-Z]?`)
  - Updated: `scripts/swarm.py` (branch → task_id parsing supports `T###A` and underscores)
- Outputs produced:
  - No new datasets; this is control-plane re-scoping + acceptance criteria.

## How to reproduce / verify

- Commands:
  - `make gate`
  - `make test`
- Expected results:
  - `make gate` passes and `task_dependencies` accepts the new task IDs (e.g., `T087A`).

## Assumptions / risks

- Assumes it’s acceptable to use split task IDs like `T087A` (letters) in the control plane. This required small updates to swarm/gate parsing to avoid treating them as invalid dependency IDs.
- T087A is the key risk reducer: it defines “blob-ready” concretely. If the probe cannot compute `burn_blob_wei` from your provider, block before attempting any backfill.

## Open questions / next steps

- Implement the probe script (`src/etl/l1_rpc_probe_blob_fields.py`) and extraction scripts in the respective tasks. Keep T087A fast (bounded scan) so failures are discovered in minutes, not hours.
