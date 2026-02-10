# Handoff H124 — T093 STR empirical full-mode artifacts blocked on missing panel input

## Summary (1–3 sentences)
T093 cannot produce `*_full` STR analysis artifacts because the required canonical input panel is missing in this worktree. The full-mode analysis command fails deterministically with `panel not found` for `data/processed/panels/daily_rollup_panel_v1.csv`. Quality gates still pass (`make gate`, `make test`).

## What changed / what exists now

- Files/paths:
  - `.orchestrator/backlog/T093_analysis_core_str_figures_full_panel.md`
    - Updated `## Status` to `State: blocked`.
    - Appended blocking evidence and required `@human` decision in `## Notes / Decisions`.
- Outputs produced:
  - No new T093 report artifacts were produced because required full-panel input is absent.

## How to reproduce / verify

- Commands:
  - `python src/analysis/str_empirical_tests.py --panel data/processed/panels/daily_rollup_panel_v1.csv --tag full`
  - `make gate`
  - `make test`
- Expected results:
  - Analysis command exits non-zero with: `panel not found: data/processed/panels/daily_rollup_panel_v1.csv`.
  - `make gate` passes all checks.
  - `make test` passes (`Ran 46 tests`, `OK`).

## Assumptions / risks

- T093 stop condition `Missing processed inputs` is active and valid.
- No fallback to sample data was used for `full` outputs to avoid violating task/protocol intent.
- This sandbox worktree has a broken `.git` pointer (`not a git repository`), so `git status`/commit SHA were unavailable for trace metadata.

## Open questions / next steps

- `@human`: provide or regenerate `data/processed/panels/daily_rollup_panel_v1.csv` in this branch/worktree, then rerun:
  - `python src/analysis/str_empirical_tests.py --panel data/processed/panels/daily_rollup_panel_v1.csv --tag full`
- After input is present, expected outputs are:
  - `reports/figures/str_time_series_full.svg`
  - `reports/tables/str_time_series_full.csv`
  - `reports/tables/str_empirical_tests_full.json`
  - `reports/tables/str_empirical_tests_full.md`
  - `reports/tables/str_empirical_tests_full_run.json`
