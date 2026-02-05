# Handoff H118 — Cross-cutting concerns: schema assertions + analysis task completeness

## Summary (1–3 sentences)

Hardened task interfaces to improve swarm safety and testability by standardizing “schema assertion” success criteria across ETL tasks, explicitly tying on-chain cost computation (T088) to the W0 contract schemas, and aligning W6 STR analysis tasks with the existing `src/analysis/str_empirical_tests.py` sample/full workflow. Added new W6 backlog tasks to cover remaining completeness gaps (decomposition, blob at-minimum/floor-binding linkage, burn vs issuance) using deterministic sample-mode artifacts.

## What changed / what exists now

- Files/paths:
  - `.orchestrator/templates/task_template_w1_w2_etl.md`: adds a standard success-criterion requiring output schema assertions.
  - `.orchestrator/backlog/T088_onchain_compute_rollup_daily_costs_and_decomposition.md`: now explicitly requires conformance to `contracts/schemas/rollup_costs_daily_v1.yaml` and `contracts/schemas/rollup_costs_decomposition_daily_v1.yaml`.
  - `.orchestrator/backlog/T030_*.md`, `T083`–`T087C`, `T089`, `T090`: added explicit schema-assertion success criteria (fail fast on missing/invalid required columns).
  - `.orchestrator/backlog/T060_analysis_str_timeseries_figure.md` and `.orchestrator/backlog/T093_analysis_core_str_figures_full_panel.md`: updated to use `src/analysis/str_empirical_tests.py` and the stable `reports/figures/str_time_series_{sample|full}.svg` / `reports/tables/str_empirical_tests_{sample|full}.*` artifact set.
  - Added backlog analysis tasks:
    - `.orchestrator/backlog/T101_analysis_rent_decomposition_plots_sample.md`
    - `.orchestrator/backlog/T102_analysis_blob_floor_binding_and_str_link_sample.md`
    - `.orchestrator/backlog/T103_analysis_burn_vs_issuance_timeseries_sample.md`
- Outputs produced:
  - No new datasets; coordination/spec changes only.

## How to reproduce / verify

- Commands:
  - `make gate`
- Expected results:
  - `task_hygiene` and `task_dependencies` pass with the updated task specs and new backlog tasks.

## Assumptions / risks

- New W6 tasks T101–T103 assume `data/samples/panels/daily_rollup_panel_v2_sample.csv` will be committed by T090; until then they remain un-runnable (by design).
- Task spec updates reference stable artifact names used by `src/analysis/str_empirical_tests.py`; if that script’s output naming changes, update the corresponding task specs to avoid drift.

## Open questions / next steps

- Implement T090 so it produces and commits `data/samples/panels/daily_rollup_panel_v2_sample.csv` (enables T101–T103).
- Consider adding a lightweight optional gate (future) that runs a small sample-mode analysis script to ensure reports remain regenerable in CI.

