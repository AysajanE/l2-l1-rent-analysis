# `contracts/schemas/`

Tracked schemas / data contracts used by the pipeline.

Placeholders you may add early:
- `panel_schema.yaml`
- `raw_<source>_schema.yaml`

Canonical schemas for this project:
- `panel_schema_str_v1.yaml` (minimum daily rollup STR panel)
- `panel_schema_str_v2.yaml` (enriched daily rollup panel for regime/macro/counterfactual work)
- `panel_schema_decomp_v1.yaml` (daily Ethereum L1 rent decomposition)
- `rollup_costs_daily_v1.yaml` (rollup-attributed on-chain rent series)
- `rollup_costs_decomposition_daily_v1.yaml` (rollup-attributed on-chain rent decomposition)
- `issuance_daily_v1.yaml` (daily gross issuance series)
