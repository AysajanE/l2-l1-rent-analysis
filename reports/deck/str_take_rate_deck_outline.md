# STR (Settlement Take Rate) — Deck Outline (W7)

This is a slide outline that references only repo-present artifacts.

## Slide 1 — Title

- “Settlement Take Rate (STR): L2→L1 rent capture and regime shifts”
- Repo: `README.md`

## Slide 2 — Definitions (protocol lock)

- STR definition + missingness rule: `docs/protocol.md`
- Universe definition: `registry/rollup_registry_v1.csv`

## Slide 3 — Data products

- Panel schema v1: `contracts/schemas/panel_schema_str_v1.yaml`
- Sample panel: `data/samples/panels/daily_rollup_panel_v1_sample.csv`
- Sample panel manifest: `data/processed_manifest/daily_rollup_panel_v1_sample_2026-02-04.json`

## Slide 4 — Empirical tests (why they matter)

- Trend test: Mann–Kendall (`src/analysis/str_empirical_tests.py`)
- Trend regression: Newey–West HAC (`src/analysis/str_empirical_tests.py`)
- Break test at Dencun boundary (`2024-03-13` UTC): `src/analysis/str_empirical_tests.py`
- Elasticity regression (log‑log): `src/analysis/str_empirical_tests.py`

## Slide 5 — Sample-mode results (pipeline check)

- Figure: `reports/figures/str_time_series_sample.svg`
- Summary: `reports/tables/str_empirical_tests_sample.md`

Note: these are synthetic results; replace with full-panel outputs when available.

## Slide 6 — Next: full-panel + v2 decomposition

- Build v1/v2 panels under `src/etl/panel_*`
- Add decomposition/regime outputs under `reports/tables/` and `reports/figures/`

