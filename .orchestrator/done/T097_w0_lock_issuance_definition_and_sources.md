---
task_id: T097
title: "W0: lock issuance definition + sources (issuance_eth)"
workstream: W0
role: Worker
priority: high
dependencies:
  - "T000"
  - "T020"
parallel_ok: false
allowed_paths:
  - "docs/protocol.md"
  - "contracts/decisions.md"
  - "contracts/assumptions.md"
  - "contracts/data_dictionary.md"
  - "contracts/schemas/issuance_daily_v1.yaml"
  - "contracts/CHANGELOG.md"
disallowed_paths:
  - "src/"
  - "registry/"
  - "data/raw/"
outputs:
  - "contracts/decisions.md"
  - "contracts/schemas/issuance_daily_v1.yaml"
  - "contracts/data_dictionary.md"
gates:
  - "make gate"
stop_conditions:
  - "Issuance definition requires new scientific assumption (block with @human)"
---

# Task T097 — W0: lock issuance definition + sources (issuance_eth)

## Context

“Issuance” is ambiguous (gross issuance vs net issuance vs supply change) and must be locked in W0 to prevent downstream ETL (W1) from making silent definition choices. The issuance series is required for burn-share context and some counterfactual framing.

This task locks:
- the canonical issuance definition (`issuance_eth`),
- primary + secondary sources,
- expected granularity and units,
and provides an explicit contract schema for W1 to implement deterministically.

## Inputs

- `docs/protocol.md` (issuance definition policy; read-only for downstream)
- Task-level feedback: `docs/feedbacks/feedback_2026-02-01.md` (critical issue #5)

## Outputs

- Decision entry: `contracts/decisions.md`
- Contract schema: `contracts/schemas/issuance_daily_v1.yaml`
- Data dictionary update: `contracts/data_dictionary.md`
- (If interfaces change) `contracts/CHANGELOG.md`

## Success Criteria

- [ ] Definition is explicit:
  - `issuance_eth` = **gross** issuance to validators (consensus-layer issuance), **not net of burn**
- [ ] Sources are explicit:
  - Primary: `ultrasound.money` daily issuance series (snapshotted)
  - Secondary: beacon-chain explorer / consensus feed (tolerance checks)
- [ ] Units + grain are explicit: daily UTC, units = ETH
- [ ] W1 issuance ETL task (T086) depends on this lock
- [ ] `make gate` passes

## Status

- State: done
- Last updated: 2026-02-05

## Notes / Decisions

- 2026-02-04: Decision + schemas landed in contracts:
  - `contracts/decisions.md` (issuance lock entry)
  - `contracts/schemas/issuance_daily_v1.yaml`
  - `contracts/data_dictionary.md`
  - `contracts/CHANGELOG.md`
- 2026-02-05: Backfilled this W0 task to make the dependency explicit; downstream task T086 now depends on T097.

