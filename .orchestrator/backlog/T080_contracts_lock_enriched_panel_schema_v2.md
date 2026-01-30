---
task_id: T080
title: "Contracts: lock enriched daily panel schema (v2)"
workstream: W0
role: Worker
priority: high
dependencies:
  - "T020"
allowed_paths:
  - "contracts/schemas/panel_schema.yaml"
  - "contracts/schemas/panel_schema_str_v2.yaml"
  - "contracts/data_dictionary.md"
  - "contracts/decisions.md"
  - "contracts/CHANGELOG.md"
disallowed_paths:
  - "src/"
  - "registry/"
  - "data/raw/"
outputs:
  - "contracts/schemas/panel_schema_str_v2.yaml"
  - "contracts/data_dictionary.md"
  - "contracts/decisions.md"
gates:
  - "make gate"
stop_conditions:
  - "Definition ambiguity"
  - "Need to reinterpret inclusion criteria"
---

# Task T080 — Contracts: lock enriched daily panel schema (v2)

## Context

The repo currently locks a minimal STR-ready contract (`contracts/schemas/panel_schema_str_v1.yaml`) that is sufficient to compute:

`STR_t = (Σ_i RentPaid_{i,t}) / (Σ_i L2Fees_{i,t})` (ETH-native primary).

For a full-scale research run we also need a stable contract for the **enriched analysis-ready daily panel** that includes:
- rollup-level on-chain rent decomposition fields,
- blob regime variables,
- optional USD conversions (explicitly labeled, secondary),
- macro inputs (price/issuance),
- provenance fields (run dates, registry version).

This task defines a versioned v2 schema (without breaking v1), updates the data dictionary accordingly, and records the schema decision + blast radius.

## Inputs

- `docs/protocol.md` (read-only): canonical definitions/units, source priority, regime rules
- `contracts/schemas/panel_schema_str_v1.yaml` and `contracts/data_dictionary.md` (existing v1 contract)
- `docs/end_to_end_data_collection_plan.md` (field inventory for the enriched panel)

## Outputs

- `contracts/schemas/panel_schema_str_v2.yaml`
  - Must clearly separate:
    - required STR-minimum fields (v1-compatible core), vs
    - optional enrichment fields (nullability + units explicit).
- `contracts/schemas/panel_schema.yaml`
  - Must reference the new versioned schema file(s) without removing v1.
- `contracts/data_dictionary.md`
  - Add/extend table entries so the enriched panel contract is unambiguous.
- `contracts/decisions.md`
  - Add a dated entry describing:
    - new field names + units + null/zero handling,
    - how v2 relates to v1 (compat/migration),
    - expected downstream impact (ETL/validation/analysis tasks).
- `contracts/CHANGELOG.md`
  - Record the interface update and why.

## Success Criteria

- [ ] `panel_schema_str_v2.yaml` exists and is internally consistent (grain, keys, units, nullable rules)
- [ ] `panel_schema.yaml` references v2 while preserving v1 as the minimum contract
- [ ] `contracts/data_dictionary.md` is updated to match the v2 schema (no drift)
- [ ] `contracts/decisions.md` includes rationale + blast radius
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-01-30

## Notes / Decisions

- 2026-01-30: Task created (Planner) to prevent schema drift before scaling ETL + analysis.
