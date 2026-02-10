# Handoff H092 — STR metrics from daily_rollup_panel v1

## Summary (1–3 sentences)

Implemented a panel-specific STR metric module and deterministic tests for the canonical v1 panel contract. The module computes ecosystem daily STR and per-rollup contribution diagnostics while enforcing protocol behavior for missingness and zero denominators. Repo gates and test suite pass.

## What changed / what exists now

- Files/paths:
  - `src/analysis/metrics_str_panel.py`
  - `tests/test_metrics_str_panel.py`
  - `.orchestrator/backlog/T092_metrics_str_from_daily_rollup_panel_and_tests.md` (Status + Notes only)
- Outputs produced:
  - `compute_daily_str_series(...)` returns daily aggregates with included/skipped counters and `str_value`.
  - `compute_rollup_str_contributions(...)` returns per-rollup diagnostics including contribution to ecosystem STR (`rent_i / sum_fees_day`).

## How to reproduce / verify

- Commands:
  - `make gate`
  - `make test`
- Expected results:
  - `make gate` reports all gates `ok=True`.
  - `make test` passes, including `tests/test_metrics_str_panel.py`.

## Assumptions / risks

- Input rows follow panel v1 key names unless caller overrides function key arguments.
- Missing numeric values are treated as missing for omission when provided as empty/`na`/`nan`/`null` strings; non-string `float('nan')` inputs are not specially normalized.

## Open questions / next steps

- If downstream analysis wants this module as the default STR source, update consuming scripts/imports explicitly in a separate task.
