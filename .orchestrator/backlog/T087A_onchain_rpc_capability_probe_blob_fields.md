---
task_id: T087A
title: "On-chain: RPC capability probe for blob fee fields (type-3 tx)"
workstream: W2
role: Worker
priority: high
dependencies:
  - "T096"
parallel_ok: false
allowed_paths:
  - "src/etl/rpc_client.py"
  - "src/etl/l1_rpc_probe_blob_fields.py"
  - "data/raw/l1/"
  - "data/raw_manifest/l1_"
  - "data/processed/l1/"
  - "data/processed_manifest/l1_"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/analysis/"
  - "src/validation/"
outputs:
  - "src/etl/rpc_client.py"
  - "src/etl/l1_rpc_probe_blob_fields.py"
  - "data/raw/l1/YYYY-MM-DD/probe/..."
  - "data/raw_manifest/l1_probe_YYYY-MM-DD.json"
  - "data/processed/l1/l1_rpc_probe_blob_fields_report.json"
  - "data/processed_manifest/l1_probe_YYYY-MM-DD.json"
gates:
  - "make gate"
stop_conditions:
  - "Need RPC credentials"
  - "No post-Dencun blob tx found in probe range"
  - "Provider does not expose required blob fields to compute burn_blob_wei deterministically"
---

# Task T087A — On-chain: RPC capability probe for blob fee fields (type-3 tx)

## Context

Before investing in a large on-chain backfill, we need a fast, concrete acceptance test that the configured RPC endpoint can expose the minimal fields required to compute blob fee burn (`burn_blob_wei`) post‑Dencun.

This task adds a tiny probe that:
- scans a small post‑Dencun block range (or a bounded “scan from latest” window),
- finds at least one type‑3 (blob) transaction,
- verifies required fields are present either in receipts, tx payloads, and/or block headers, and
- computes `burn_blob_wei` deterministically using integer wei math per `docs/protocol.md`.

Downstream tasks (T087B/T087C) must depend on this probe so the swarm fails fast if blob fields are unavailable.

## Inputs

- RPC endpoint via `ETH_RPC_URL` (do not commit secrets)
- `docs/protocol.md` (read-only): blob fee computation rules and Dencun boundary (`2024-03-13` UTC)
- `scripts/make_raw_manifest.py` (for raw snapshot manifest)
- `scripts/make_processed_manifest.py` (for processed manifest; T096)

## Outputs

- Code:
  - `src/etl/rpc_client.py` (shared, minimal RPC client)
  - `src/etl/l1_rpc_probe_blob_fields.py` (probe CLI)
- Raw snapshots (append-only; not committed): `data/raw/l1/<YYYY-MM-DD>/probe/...`
- Raw manifest (tracked): `data/raw_manifest/l1_probe_<YYYY-MM-DD>.json`
- Probe report (not committed): `data/processed/l1/l1_rpc_probe_blob_fields_report.json`
- Processed manifest (tracked): `data/processed_manifest/l1_probe_<YYYY-MM-DD>.json`

## Success Criteria

- [ ] Preflight passes: `make preflight-onchain`
- [ ] Probe finds at least one blob tx: `tx_type == 3`
- [ ] For at least one blob tx, the probe can obtain:
  - `blob_gas_used` either from receipt field `blobGasUsed` (preferred) **or** from `len(blobVersionedHashes) * 131072`
  - `base_fee_per_blob_gas_wei` either from receipt field `blobGasPrice` (preferred) **or** computed deterministically from block header fields per EIP‑4844
- [ ] Probe computes `burn_blob_wei = blob_gas_used * base_fee_per_blob_gas_wei` as an integer (wei) and records it in the report
- [ ] Raw + processed manifests are append-only and record inputs + output hashes (processed manifest generated via `python scripts/make_processed_manifest.py ...`)
- [ ] `make gate` passes

## Validation / Commands

- `make preflight-onchain`
- Example probe run (bounded scan; choose parameters to reliably hit post‑Dencun blocks):
  - `python src/etl/l1_rpc_probe_blob_fields.py --as-of 2026-02-04 --scan-latest-blocks 2048 --out data/processed/l1/l1_rpc_probe_blob_fields_report.json --write-manifest`

## Status

- State: backlog
- Last updated: 2026-02-04

## Notes / Decisions

- 2026-02-04: Split from the original monolithic T087 per task-level feedback; this probe defines a concrete “blob-ready” acceptance test.

