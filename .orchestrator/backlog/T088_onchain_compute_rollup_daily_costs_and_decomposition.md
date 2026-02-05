---
task_id: T088
title: "On-chain: compute rollup-attributed daily rent + decomposition tables"
workstream: W2
role: Worker
priority: high
dependencies:
  - "T096"
  - "T082"
  - "T087B"
  - "T087C"
parallel_ok: false
allowed_paths:
  - "src/etl/l1_fee_components.py"
  - "src/etl/l1_rollup_costs.py"
  - "data/processed/onchain/"
  - "data/processed_manifest/onchain_"
  - "data/samples/l1/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/analysis/"
  - "src/validation/"
outputs:
  - "src/etl/l1_fee_components.py"
  - "src/etl/l1_rollup_costs.py"
  - "data/processed/onchain/rollup_costs_daily.parquet"
  - "data/processed/onchain/rollup_costs_decomposition_daily.parquet"
  - "data/processed_manifest/onchain_rollup_costs_YYYY-MM-DD.json"
  - "data/samples/l1/rollup_costs_daily_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Attribution ambiguity requires @human"
  - "Validation failure beyond protocol tolerances (block)"
---

# Task T088 — On-chain: compute rollup-attributed daily rent + decomposition tables

## Context

Per `docs/protocol.md`, on-chain computed series are authoritative for `RentPaid_{i,t}` and its decomposition. Using the raw extraction from T087B/T087C and the attribution registry from T082, compute:
- daily rollup-attributed rent in ETH, and
- a decomposition into burn vs tips, and blob vs execution where feasible.

Outputs should be rebuildable from raw snapshots and should include a committed tiny sample for deterministic downstream testing.

## Inputs

- `registry/rollup_registry_v1.csv` (read-only): batcher/poster addresses and evidence
- Raw/processed L1 extracts from T087B/T087C (read-only)
- `docs/protocol.md` (read-only): Dencun boundary, tolerances, and decomposition expectations
- Contracts (read-only; do not reinterpret fields/units):
  - `contracts/schemas/rollup_costs_daily_v1.yaml`
  - `contracts/schemas/rollup_costs_decomposition_daily_v1.yaml`

## Outputs

- Computation code:
  - `src/etl/l1_fee_components.py` (per-tx fee breakdown helpers)
  - `src/etl/l1_rollup_costs.py` (rollup attribution + daily aggregation)
- Processed tables (not committed):
  - `data/processed/onchain/rollup_costs_daily.parquet`
    - include at minimum: `date_utc`, `rollup_id`, `rent_paid_eth`
    - must conform to `contracts/schemas/rollup_costs_daily_v1.yaml`
  - `data/processed/onchain/rollup_costs_decomposition_daily.parquet`
    - include component columns with explicit units (ETH) and clear nullability rules.
    - for precision safety, also include the integer-safe wei columns defined in the contract:
      `rent_paid_wei`, `rent_base_fee_burn_wei`, `rent_blob_fee_burn_wei`, `rent_priority_fee_wei`
    - do not compute or store blob fee components using floating-point gwei; use integer wei inputs per `docs/protocol.md`.
    - must conform to `contracts/schemas/rollup_costs_decomposition_daily_v1.yaml`
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
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` and includes input manifests + output hashes
- [ ] Sample is committed and stable
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-02-05

## Notes / Decisions

- 2026-01-30: Task created (Planner) to produce the authoritative on-chain rent series required for STR.
- 2026-02-05: Explicitly required conformance to the W0 on-chain rollup cost contracts to prevent schema drift.
