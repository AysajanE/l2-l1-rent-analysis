# `data/samples/panels/` — golden sample panels

This folder contains **small, tracked** panel datasets used to validate analysis/ETL deterministically.

## Files

- `daily_rollup_panel_v1_sample.csv`
  - Contract: `contracts/schemas/panel_schema_str_v1.yaml`
  - Purpose: enable `--sample` modes for panel builders and analysis scripts.
  - Coverage: uses the repo’s canonical sample window (see `data/samples/README.md`), spanning the Dencun boundary (`2024-03-13` UTC) and including a full post‑Dencun month.

- `daily_rollup_panel_v2_sample.csv`
  - Contract: `contracts/schemas/panel_schema_str_v2.yaml`
  - Purpose: enable `--sample` modes for v2-enriched analysis scripts (e.g., EIP-7918 counterfactuals).
  - Coverage: same canonical window + rollup subset as v1.
  - Notes:
    - v2-only blob-regime fields in this sample are **synthetic but deterministic** (for CI):
      - `l1_base_fee_per_gas_wei` is fixed at 48 gwei.
      - Post‑Dencun `l1_blob_base_fee_wei` alternates by day-of-month (odd→4 gwei, even→2 gwei), creating “floor binding” days for tests.
      - Post‑Dencun `rollup_blob_gas_used` is a fixed 6000 blobs worth of blob gas per rollup-day; `rent_blob_fee_burn_wei` is computed as `blob_gas_used * blob_base_fee`.
