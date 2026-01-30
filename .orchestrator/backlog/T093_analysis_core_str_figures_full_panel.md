---
task_id: T093
title: "Analysis: generate core STR figure set from v1 panel"
workstream: W6
role: Worker
priority: medium
dependencies:
  - "T089"
  - "T091"
  - "T092"
allowed_paths:
  - "src/analysis/plot_str_timeseries_full.py"
  - "reports/figures/str_timeseries_full.svg"
  - "reports/tables/str_summary_full.csv"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/etl/"
  - "data/raw/"
outputs:
  - "src/analysis/plot_str_timeseries_full.py"
  - "reports/figures/str_timeseries_full.svg"
  - "reports/tables/str_summary_full.csv"
gates:
  - "make gate"
stop_conditions:
  - "Missing processed inputs"
---

# Task T093 — Analysis: generate core STR figure set from v1 panel

## Context

Produce the first full-scale research artifacts derived from the canonical v1 daily panel:
- aggregate STR time series (annotated with Dencun date),
- simple summary table for top rollups / regimes (as available).

This task is intentionally constrained emphasizes:
- no network calls,
- deterministic outputs,
- stable artifact paths under `reports/`.

## Inputs

- `data/processed/panels/daily_rollup_panel_v1.parquet` (not committed; built by T089)
- `src/analysis/metrics_str_panel.py` (read-only; built by T092)
- `reports/validation/cross_source_validation.json` (read-only; built by T091; used for annotation or gating)

## Outputs

- `src/analysis/plot_str_timeseries_full.py`
  - Loads the v1 panel and writes outputs deterministically.
- `reports/figures/str_timeseries_full.svg`
- `reports/tables/str_summary_full.csv`
  - Include at minimum: date window, aggregate STR, and a small set of regime annotations if available.

## Success Criteria

- [ ] Artifacts are generated from local processed inputs only (no network)
- [ ] Outputs are deterministic and reproducible via a single command
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-01-30

## Notes / Decisions

- 2026-01-30: Task created (Planner) to produce the core full-scale STR results artifacts.

