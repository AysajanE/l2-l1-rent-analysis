# Universe coverage report

- Status: **PASS**
- Mode: `sample`
- Post-Dencun boundary: `2024-03-13`

## Inputs
- `registry`: `registry/rollup_registry_v1.csv` (exists=True, required=True)
- `rollup_costs_daily`: `data/samples/l1/rollup_costs_daily_sample.csv` (exists=True, required=True)
- `rollup_blob_usage`: `data/samples/panels/daily_rollup_panel_v2_sample.csv` (exists=True, required=True)
- `l1_blob_baseline`: `data/samples/panels/daily_rollup_panel_v2_sample.csv` (exists=True, required=True)
- `blobscan_optional`: `data/samples/blobscan/blobscan_daily_sample.csv` (exists=True, required=False)

## Registry readiness
- in_scope_rollup_count: 13
- active_in_scope_rollup_count_in_observed_post_dencun_window: 13
- total_address_count: 53
- address_coverage_state_counts: {'complete': 13}

## Attribution coverage (post-Dencun)
- dates_with_l1_blob_baseline: 49
- dates_with_rollup_blob_usage: 49
- dates_missing_rollup_blob_usage: 0
- sum_rollup_blob_gas_used: 115605504000
- sum_l1_blob_gas_used: 115605504000
- rollup_to_l1_blob_gas_ratio: 1.0
- sum_rollup_blob_fee_burn_eth: 349.175808
- sum_l1_blob_fee_burn_proxy_eth: 349.175808
- rollup_to_l1_blob_fee_burn_ratio: 1.0

## Gaps
- rollups_with_unknown_state: []
- rollups_with_partial_state: []
- rollup_ids_not_in_registry: []
- coverage_drop_dates: []
