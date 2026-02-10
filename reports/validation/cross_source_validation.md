# Cross-source validation

- Status: **FAIL**
- Mode: `sample`

## Inputs
- `growthepie`: `data/samples/growthepie/vendor_daily_rollup_panel_sample.csv` (exists=True, required=True)
- `onchain`: `data/samples/panels/daily_rollup_panel_v1_sample.csv` (exists=True, required=True)
- `l2beat`: `data/samples/l2beat/l2beat_costs_daily_sample.csv` (exists=True, required=True)
- `blobscan`: `data/samples/blobscan/blobscan_daily_sample.csv` (exists=True, required=False)
- `onchain_blob`: `data/samples/panels/daily_rollup_panel_v2_sample.csv` (exists=True, required=False)

## Metrics
- records_total: 27
- records_le_5pct: 16
- records_between_5pct_10pct: 0
- records_gt_10pct: 2
- top_rollup_count: 3
- blob_gas_used_check_status: evaluated
- blob_selected_month_utc: 2024-04
- blob_days_compared: 30
- blob_days_gt_1pct: 30
- unknown_unattributed_rollups: {'growthepie': [], 'onchain': [], 'l2beat': []}

## Failures
- [monthly_reconciliation] delta_gt_10pct (arbitrum @ 2024-04)
- [monthly_reconciliation] delta_gt_10pct (arbitrum @ 2024-04)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-01)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-02)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-03)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-04)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-05)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-06)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-07)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-08)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-09)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-10)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-11)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-12)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-13)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-14)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-15)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-16)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-17)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-18)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-19)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-20)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-21)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-22)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-23)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-24)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-25)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-26)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-27)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-28)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-29)
- [blob_gas_used_reconciliation] delta_gt_1pct (2024-04-30)

## Plausible causes
- Source-window mismatch or stale snapshots (different extraction dates/ranges).
- Rollup identifier mapping drift between vendor/on-chain/L2BEAT joins.
- Attribution coverage differences (especially blob-heavy days).

## Minimal next experiment
- Pick one failing rollup-month and compare daily values side-by-side from all sources, then verify ID mapping and source run dates.
