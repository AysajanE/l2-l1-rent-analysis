---
task_id: T091
title: "Validation: cross-source reconciliation (growthepie vs on-chain vs L2BEAT; Blobscan sanity)"
workstream: W5
role: Worker
priority: high
dependencies:
  - "T083"
  - "T084"
  - "T089"
gates:
  - "make gate"
stop_conditions:
  - "Validation failure beyond tolerance"
allowed_paths:
  - "src/validation/validate_cross_source.py"
  - "reports/validation/cross_source_validation.json"
  - "reports/validation/cross_source_validation.md"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/etl/"
  - "data/raw/"
outputs:
  - "src/validation/validate_cross_source.py"
  - "reports/validation/cross_source_validation.json"
  - "reports/validation/cross_source_validation.md"
---

# Task T091 — Validation: cross-source reconciliation (growthepie vs on-chain vs L2BEAT; Blobscan sanity)

## Context

Full-scale results require reconciliation across:
- growthepie (vendor series; primary for `L2Fees`, secondary for `rent_paid/profit`),
- on-chain computed rollup rent (authoritative for `RentPaid`),
- L2BEAT costs (triangulation),
- Blobscan aggregates (blob usage cross-checks).

This task implements deterministic validation scripts and emits both machine-readable JSON and a short human-facing report.

## Inputs

- `docs/protocol.md` (read-only): tolerances and regime definitions
- Processed tables produced by:
  - T083 (L2BEAT)
  - T084 (Blobscan)
  - T089 (v1 daily_rollup_panel; includes on-chain rent + growthepie fees)

## Outputs

- `src/validation/validate_cross_source.py`
  - Deterministic; no network calls.
  - Should support:
    - `--sample` mode (uses committed samples if present)
    - `--full` mode (reads from `data/processed/`)
  - Must follow the repo validation CLI contract (`src/validation/AGENTS.md`):
    - exit codes: `0` pass, `2` fail (beyond tolerance), `3` missing required inputs/schema mismatch
    - strict JSON summary with keys: `ok`, `inputs`, `metrics`, `failures`
- `reports/validation/cross_source_validation.json`
  - Include pass/fail + key metrics:
    - monthly reconciliation deltas for top rollups
    - blobGasUsed tolerance check on a sample month (Blobscan vs on-chain extraction, if both available)
  - `failures[]` entries must include pointers to offending rows (date/rollup) where applicable.
- `reports/validation/cross_source_validation.md`
  - Summarize findings and the smallest next experiment if something fails.

## Success Criteria

- [ ] Validation respects protocol tolerances (no invented thresholds)
- [ ] Reports are deterministic and reproducible from local inputs only
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-02-05

## Notes / Decisions

- 2026-01-30: Task created (Planner) to enforce “anti-dashboard-science” cross-source reconciliation before analysis.
