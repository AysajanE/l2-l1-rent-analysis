---
task_id: T098
title: "W0: lock EIP-7918 reserve/floor counterfactual assumptions + parameterization"
workstream: W0
role: Worker
priority: high
dependencies:
  - "T000"
parallel_ok: false
allowed_paths:
  - "docs/protocol.md"
  - "contracts/decisions.md"
  - "contracts/assumptions.md"
  - "contracts/data_dictionary.md"
  - "contracts/schemas/panel_schema_str_v2.yaml"
  - "contracts/CHANGELOG.md"
disallowed_paths:
  - "src/"
  - "registry/"
  - "data/raw/"
outputs:
  - "docs/protocol.md"
  - "contracts/decisions.md"
  - "contracts/assumptions.md"
gates:
  - "make gate"
stop_conditions:
  - "Counterfactual requires a new scientific assumption (block with @human)"
---

# Task T098 — W0: lock EIP-7918 reserve/floor counterfactual assumptions + parameterization

## Context

The EIP-7918 reserve/floor counterfactual is a **scientific/definition choice** and must be locked in W0 (protocol + contracts) so downstream analysis (T094) can implement deterministically without inventing parameters at runtime.

This task locks:
- the reserve-price parameterization (constants + formulas),
- what “floor binding” means, and
- the modeling assumption that the counterfactual is an applied floor on the observed series (not an equilibrium simulation).

## Inputs

- `docs/feedbacks/feedback_2026-02-01.md` (revision item #6)
- `docs/protocol.md`
- `contracts/decisions.md`
- `contracts/assumptions.md`
- `contracts/schemas/panel_schema_str_v2.yaml` (required observed inputs; e.g., `l1_base_fee_per_gas_wei`)

## Outputs

- Protocol lock entry (canonical formulas + constants): `docs/protocol.md`
- Decision log entry (blast radius + field names): `contracts/decisions.md`
- Assumption registry entry: `contracts/assumptions.md`

## Success Criteria

- [ ] Protocol includes explicit EIP-7918 parameterization (constants + formulas)
- [ ] Contracts record the modeling assumption (applied floor on observed series) and do not leave interpretation to W6
- [ ] Required observed inputs are present in v2 schema/data dictionary (execution base fee series in integer wei)
- [ ] Downstream counterfactual task (T094) depends on this lock
- [ ] `make gate` passes

## Status

- State: done
- Last updated: 2026-02-05

## Notes / Decisions

- 2026-02-04: Protocol/contracts lock landed:
  - `docs/protocol.md` includes EIP-7918 reserve-floor parameterization (constants + formulas + “binding” definition).
  - `contracts/decisions.md` records EIP-7918 parameterization and required input fields.
  - `contracts/assumptions.md` includes A001 (applied-floor counterfactual; not equilibrium simulation).
- 2026-02-05: Backfilled this W0 task to make the dependency explicit; downstream task T094 now depends on T098.

