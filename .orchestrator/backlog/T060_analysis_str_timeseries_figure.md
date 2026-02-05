---
task_id: T060
title: "Analysis: generate STR time series + empirical tests (sample mode)"
workstream: W6
role: Worker
priority: medium
dependencies:
  - "T040"
  - "T050"
allowed_paths:
  - "src/analysis/str_empirical_tests.py"
  - "reports/figures/str_time_series_sample.svg"
  - "reports/tables/str_time_series_sample.csv"
  - "reports/tables/str_empirical_tests_sample.json"
  - "reports/tables/str_empirical_tests_sample.md"
  - "reports/tables/str_empirical_tests_sample_run.json"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "src/etl/"
  - "src/analysis/metrics_str.py"
  - "data/raw/"
outputs:
  - "src/analysis/str_empirical_tests.py"
  - "reports/figures/str_time_series_sample.svg"
  - "reports/tables/str_time_series_sample.csv"
  - "reports/tables/str_empirical_tests_sample.json"
  - "reports/tables/str_empirical_tests_sample.md"
  - "reports/tables/str_empirical_tests_sample_run.json"
gates:
  - "make gate"
stop_conditions:
  - "Missing sample inputs"
---

# Task T060 — Analysis: generate STR time series + empirical tests (sample mode)

## Context

Create the first “vertical slice” research output artifact set generated from deterministic sample inputs:
- STR time series (figure + CSV), and
- basic empirical STR tests (trend + Dencun break + simple elasticity scaffolding).

This is primarily a workflow test:
- analysis code reads local inputs only (no network),
- outputs go to `reports/figures/`,
- and the figure can be regenerated via a single command.

## Inputs

- `data/samples/panels/daily_rollup_panel_v1_sample.csv` (committed; produced/maintained by W9)
- `src/analysis/metrics_str.py` (read-only; produced by T040)
- `reports/validation/vendor_panel_validation.json` (optional; used to gate/annotate)

## Outputs

- `src/analysis/str_empirical_tests.py`
  - Deterministic (no randomness; no network).
  - Must support `--sample` mode and write stable sample-tagged artifacts under `reports/`.
- Generated artifacts (stable names; committed):
  - `reports/figures/str_time_series_sample.svg`
  - `reports/tables/str_time_series_sample.csv`
  - `reports/tables/str_empirical_tests_sample.json`
  - `reports/tables/str_empirical_tests_sample.md`
  - `reports/tables/str_empirical_tests_sample_run.json` (traceability: command, versions, hashes)

## Success Criteria

- [ ] Running the script in sample mode produces the stable artifacts under `reports/figures/` and `reports/tables/`
- [ ] Output is deterministic for the committed sample
- [ ] `make gate` passes

## Validation / Commands

- `make gate`
- Example:
  - `python src/analysis/str_empirical_tests.py --sample`

## Status

- State: backlog
- Last updated: 2026-01-22

## Notes / Decisions

- 2026-01-22: Task created (Planner) to produce the first reproducible figure artifact.
