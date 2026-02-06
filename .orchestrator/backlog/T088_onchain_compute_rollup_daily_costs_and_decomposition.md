---
task_id: T088
title: "On-chain: compute rollup-attributed daily rent + decomposition tables (BigQuery-first)"
workstream: W2
role: Worker
priority: high
dependencies:
  - "T096"
  - "T082"
parallel_ok: false
allowed_paths:
  - "src/etl/l1_rollup_costs_bigquery.py"
  - "data/processed/onchain/"
  - "data/raw_manifest/bq_ethereum_rollup_costs_"
  - "data/processed_manifest/onchain_"
  - "data/samples/l1/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/analysis/"
  - "src/validation/"
outputs:
  - "src/etl/l1_rollup_costs_bigquery.py"
  - "data/processed/onchain/rollup_costs_daily.csv"
  - "data/processed/onchain/rollup_costs_decomposition_daily.csv"
  - "data/raw_manifest/bq_ethereum_rollup_costs_<YYYY-MM-DD>.json"
  - "data/processed_manifest/onchain_rollup_costs_YYYY-MM-DD.json"
  - "data/samples/l1/rollup_costs_daily_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Attribution ambiguity requires @human"
  - "Validation failure beyond protocol tolerances (block)"
---

# Task T088 — On-chain: compute rollup-attributed daily rent + decomposition tables (BigQuery-first)

## Context

Per `docs/protocol.md`, on-chain computed series are authoritative for `RentPaid_{i,t}` and its decomposition. This repo’s preferred unattended extraction route is **BigQuery**, attributing txs to rollups via the registry sender allowlist.

Using BigQuery public Ethereum tables + the attribution registry from T082, compute:
- daily rollup-attributed rent in ETH, and
- a decomposition into burn vs tips, and blob vs execution where feasible.

Outputs should be rebuildable from raw snapshots (SQL + query outputs) and should include a committed tiny sample for deterministic downstream testing.

## Inputs

- `registry/rollup_registry_v1.csv` (read-only): batcher/poster sender allowlist and evidence (T082)
- `docs/protocol.md` (read-only): Dencun boundary, tolerances, and decomposition expectations
- Contracts (read-only; do not reinterpret fields/units):
  - `contracts/schemas/rollup_costs_daily_v1.yaml`
  - `contracts/schemas/rollup_costs_decomposition_daily_v1.yaml`

## Outputs

- BigQuery ETL code:
  - `src/etl/l1_rollup_costs_bigquery.py` (BigQuery query + rollup attribution + daily aggregation)
- Raw manifest (tracked): `data/raw_manifest/bq_ethereum_rollup_costs_<YYYY-MM-DD>.json`
- Processed tables (not committed): `data/processed/onchain/*.csv`
  - `data/processed/onchain/rollup_costs_daily.csv`
  - `data/processed/onchain/rollup_costs_decomposition_daily.csv`
  - Must conform to the on-chain rollup cost contracts (field names + nullability + units).
- Processed manifest (tracked): `data/processed_manifest/onchain_rollup_costs_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/l1/rollup_costs_daily_sample.csv`
  - small fixed window + subset of rollups; enough to validate attribution logic deterministically.
  - Prefer the repo’s canonical sample window + rollup subset (see `data/samples/README.md`) where feasible.

## Success Criteria

- [ ] Daily rollup rent series is reproducible from raw snapshots + registry version
- [ ] Decomposition components are internally consistent (sum checks where applicable)
- [ ] Outputs conform to the on-chain rollup cost contracts (field names + nullability + units):
  - `contracts/schemas/rollup_costs_daily_v1.yaml`
  - `contracts/schemas/rollup_costs_decomposition_daily_v1.yaml`
- [ ] BigQuery preflight passes: `make preflight-bigquery`
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` and includes input manifests + output hashes
- [ ] Sample is committed and stable
- [ ] `make gate` passes

## Status
- State: active
- Last updated: 2026-02-06
## Notes / Decisions

- 2026-01-30: Task created (Planner) to produce the authoritative on-chain rent series required for STR.
- 2026-02-05: Explicitly required conformance to the W0 on-chain rollup cost contracts to prevent schema drift.


- 2026-02-06: Claimed by swarm runner; starting worker (branch: T088_onchain_compute_rollup_daily_costs_and_decomposition).
