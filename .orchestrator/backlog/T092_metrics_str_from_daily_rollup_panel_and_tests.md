---
task_id: T092
title: "Metrics: STR computation from daily_rollup_panel (v1) + unit tests"
workstream: W4
role: Worker
priority: high
dependencies:
  - "T089"
allowed_paths:
  - "src/analysis/metrics_str_panel.py"
  - "tests/test_metrics_str_panel.py"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "src/etl/"
  - "data/raw/"
outputs:
  - "src/analysis/metrics_str_panel.py"
  - "tests/test_metrics_str_panel.py"
gates:
  - "make gate"
  - "make test"
stop_conditions:
  - "Contract ambiguity"
---

# Task T092 — Metrics: STR computation from daily_rollup_panel (v1) + unit tests

## Context

Implement the primary metric from `docs/protocol.md` against the canonical v1 panel:

- `STR_t = (Σ_i RentPaid_{i,t}) / (Σ_i L2Fees_{i,t})`

Unlike the initial pilot metric task (sample-only), this task targets the **post-join panel contract** produced by T089 and validates behavior with deterministic unit tests.

## Inputs

- `docs/protocol.md` (read-only): STR definition + denominator/missingness rules
- `contracts/schemas/panel_schema_str_v1.yaml` (read-only): required field names/units
- `data/samples/panels/daily_rollup_panel_v1_sample.csv` (committed by T089)

## Outputs

- `src/analysis/metrics_str_panel.py`
  - Deterministic and pure (no I/O except loading inputs passed in).
  - Provide helpers to:
    - compute daily aggregate STR time series,
    - compute per-rollup STR contribution diagnostics (optional but useful for validation).
- `tests/test_metrics_str_panel.py`
  - Tests should cover:
    - basic STR computation on a tiny fixture,
    - denominator-zero behavior (`STR_t = NaN`),
    - missingness rule (row omission).

## Success Criteria

- [ ] Implementation matches protocol definition (ETH-native primary)
- [ ] Tests are deterministic and cover edge cases explicitly
- [ ] `make gate` and `make test` pass

## Status
- State: active
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-01-30: Task created (Planner) to lock STR math on the canonical joined panel before full-scale analysis.



- 2026-02-10: Claimed by swarm runner; starting worker (branch: T092_metrics_str_from_daily_rollup_panel_and_tests).
