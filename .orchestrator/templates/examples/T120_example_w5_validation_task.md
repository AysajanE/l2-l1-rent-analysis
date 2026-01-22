---
task_id: T120
title: "Example W5 validation task (produce MD + JSON report)"
workstream: W5
role: Worker
priority: medium
dependencies: []
allowed_paths:
  - "src/validation/"
  - "reports/validation/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "src/etl/"
outputs:
  - "src/validation/validate_example.py"
  - "reports/validation/example_validation.json"
  - "reports/validation/example_validation.md"
gates:
  - "make gate"
stop_conditions:
  - "Validation failure beyond tolerance"
---

# Task T120 — Example W5 validation task (produce MD + JSON report)

## Context

Create a deterministic validation check that consumes local artifacts and emits a machine-readable JSON summary plus a short human-readable Markdown report.

## Assignment

- Workstream: W5 Validation
- Owner (agent/human):
- Suggested branch/worktree name: `T120_example_w5_validation`
- Allowed paths (edit/write): `src/validation/`, `reports/validation/`
- Disallowed paths: `docs/protocol.md`, `contracts/`, `src/etl/`
- Stop conditions (escalate + block with `@human`):
  - Validation fails beyond tolerance specified in `docs/protocol.md`

## Inputs

- Processed data artifacts under `data/processed/` (local; not fetched during validation)
- Tolerances from `docs/protocol.md`

## Outputs

- `reports/validation/<name>.json` — summary suitable for automation
- `reports/validation/<name>.md` — short narrative with next steps if failing

## Success Criteria

- [ ] Deterministic (no network calls, fixed seeds if needed)
- [ ] JSON includes pass/fail + key metrics + pointers to inputs
- [ ] `make gate` passes

## Validation / Commands

- `make gate`

## Status

- State: backlog | active | blocked | ready_for_review | done
- Last updated: YYYY-MM-DD

## Notes / Decisions

- YYYY-MM-DD: Example notes go here.
