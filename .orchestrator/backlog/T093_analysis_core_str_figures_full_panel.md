---
task_id: T093
title: "Analysis: generate STR time series + empirical tests from v1 panel (full mode)"
workstream: W6
role: Worker
priority: medium
dependencies:
  - "T040"
  - "T089"
  - "T091"
allowed_paths:
  - "src/analysis/str_empirical_tests.py"
  - "reports/figures/str_time_series_full.svg"
  - "reports/tables/str_time_series_full.csv"
  - "reports/tables/str_empirical_tests_full.json"
  - "reports/tables/str_empirical_tests_full.md"
  - "reports/tables/str_empirical_tests_full_run.json"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/etl/"
  - "data/raw/"
outputs:
  - "src/analysis/str_empirical_tests.py"
  - "reports/figures/str_time_series_full.svg"
  - "reports/tables/str_time_series_full.csv"
  - "reports/tables/str_empirical_tests_full.json"
  - "reports/tables/str_empirical_tests_full.md"
  - "reports/tables/str_empirical_tests_full_run.json"
gates:
  - "make gate"
stop_conditions:
  - "Missing processed inputs"
---

# Task T093 — Analysis: generate STR time series + empirical tests from v1 panel (full mode)

## Context

Produce full-scale research artifacts derived from the canonical v1 daily panel:
- aggregate STR time series (annotated with Dencun date), and
- core empirical tests (trend + Dencun break + simple elasticity scaffolding).

This task is intentionally constrained emphasizes:
- no network calls,
- deterministic outputs,
- stable artifact paths under `reports/`.

## Inputs

- `data/processed/panels/daily_rollup_panel_v1.csv` (not committed; built by T089)
- `src/analysis/metrics_str.py` (read-only; built by T040)
- `reports/validation/cross_source_validation.json` (read-only; built by T091; used for annotation or gating)

## Outputs

- `src/analysis/str_empirical_tests.py`
  - Must support full mode via `--panel <path>` and write stable full-tagged artifacts under `reports/`.
- Generated artifacts (stable names; may be committed when publishing):
  - `reports/figures/str_time_series_full.svg`
  - `reports/tables/str_time_series_full.csv`
  - `reports/tables/str_empirical_tests_full.json`
  - `reports/tables/str_empirical_tests_full.md`
  - `reports/tables/str_empirical_tests_full_run.json` (traceability: command, versions, hashes)

## Success Criteria

- [ ] Artifacts are generated from local processed inputs only (no network)
- [ ] Outputs are deterministic and reproducible via a single command
- [ ] `make gate` passes

## Status
- State: active
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-01-30: Task created (Planner) to produce the core full-scale STR results artifacts.


- 2026-02-10: Claimed by swarm runner; starting worker (branch: T093_analysis_core_str_figures_full_panel).
