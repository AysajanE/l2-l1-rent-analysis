# Handoff H087A — On-chain RPC blob-field capability probe

## Summary (1–3 sentences)
Executed the L1 RPC blob-field probe against `ETH_RPC_URL` and verified end-to-end capability to compute integer-safe `burn_blob_wei` for a type-3 transaction. The probe found a blob tx, derived required fields from receipt data, wrote append-only raw snapshots, and emitted raw/processed manifests for reproducibility. Task gates and tests passed.

## What changed / what exists now

- Files/paths:
- `.orchestrator/backlog/T087A_onchain_rpc_capability_probe_blob_fields.md`
- `data/raw/l1/2026-02-04/probe/block_0x174b55c.json`
- `data/raw/l1/2026-02-04/probe/tx_0x3b486e493ee9f20c3999fa9a2c5aa77e3ea5cfef1ff68260f027aa178bbe6100.json`
- `data/raw/l1/2026-02-04/probe/receipt_0x3b486e493ee9f20c3999fa9a2c5aa77e3ea5cfef1ff68260f027aa178bbe6100.json`
- `data/raw_manifest/l1_probe_2026-02-04.json`
- `data/processed/l1/l1_rpc_probe_blob_fields_report.json`
- `data/processed_manifest/l1_probe_2026-02-04.json`

- Outputs produced:
- Type-3 tx found: `0x3b486e493ee9f20c3999fa9a2c5aa77e3ea5cfef1ff68260f027aa178bbe6100`
- `blob_gas_used`: `131072` (source: `receipt.blobGasUsed`)
- `base_fee_per_blob_gas_wei`: `3755074` (source: `receipt.blobGasPrice`)
- `burn_blob_wei`: `492185059328`

## How to reproduce / verify

- Commands:
- `make preflight-onchain`
- `python src/etl/l1_rpc_probe_blob_fields.py --as-of 2026-02-04 --scan-latest-blocks 2048 --out data/processed/l1/l1_rpc_probe_blob_fields_report.json --write-manifest`
- `make gate`
- `make test`

- Expected results:
- Preflight passes with `ETH_RPC_URL` present.
- Probe report sets `ok=true` and `acceptance.can_compute_burn_blob_wei=true`.
- Raw manifest and processed manifest are created at `data/raw_manifest/l1_probe_2026-02-04.json` and `data/processed_manifest/l1_probe_2026-02-04.json`.
- `make gate` passes; `make test` passes (`Ran 42 tests ... OK`).

## Assumptions / risks

- This run used a bounded latest-block scan (`2048` blocks) and depends on provider visibility of type-3 txs in that window.
- Sandbox git worktree metadata is unavailable in this environment, so `data/processed_manifest/l1_probe_2026-02-04.json` records `transform.git_sha = null`.
- Raw/processed artifacts under `data/raw/` and `data/processed/` are intentionally untracked per repo policy.

## Open questions / next steps

- T087B/T087C can proceed using this probe output as the fast-fail capability check for blob fields.
