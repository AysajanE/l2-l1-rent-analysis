# Handoff H115 — W0 issuance definition lock task (T097) + wire T086 dependency

## Summary (1–3 sentences)

Added an explicit W0 control-plane task (T097) capturing the locked issuance definition/sources and wired the W1 issuance ETL task (T086) to depend on it. This removes “issuance definition” ambiguity from W1 and keeps definition choices in W0 contracts/decisions.

## What changed / what exists now

- Files/paths:
  - Added: `.orchestrator/done/T097_w0_lock_issuance_definition_and_sources.md`
  - Updated: `.orchestrator/backlog/T086_issuance_etl_daily_and_sample.md` (depends on T097; context/inputs now reference locked contract; removed definition-ambiguity stop condition)
- Outputs produced:
  - No new datasets; this is task sequencing + documentation to prevent definition drift.

## How to reproduce / verify

- Commands:
  - `make gate`
  - `make test`
- Expected results:
  - `make gate` passes and `task_dependencies` confirms T086 depends on T097.

## Assumptions / risks

- Assumes the issuance lock already exists in W0 artifacts:
  - `docs/protocol.md` issuance definition section,
  - `contracts/decisions.md` issuance decision entry,
  - `contracts/schemas/issuance_daily_v1.yaml`,
  - `contracts/data_dictionary.md`.

## Open questions / next steps

- When implementing T086 ETL, enforce the contract fields (`date_utc`, `issuance_eth`, `source`, optional `method`) and keep the primary/secondary source policy unchanged unless a W0 follow-up explicitly revises it.
