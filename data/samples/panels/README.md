# `data/samples/panels/` — golden sample panels

This folder contains **small, tracked** panel datasets used to validate analysis/ETL deterministically.

## Files

- `daily_rollup_panel_v1_sample.csv`
  - Contract: `contracts/schemas/panel_schema_str_v1.yaml`
  - Purpose: enable `--sample` modes for panel builders and analysis scripts.
  - Coverage: uses the repo’s canonical sample window (see `data/samples/README.md`), spanning the Dencun boundary (`2024-03-13` UTC) and including a full post‑Dencun month.
