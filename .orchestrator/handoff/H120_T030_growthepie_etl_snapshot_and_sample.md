# Handoff H120 — T030 growthepie ETL snapshot + golden sample

## Summary (1–3 sentences)
T030 W1 outputs were completed in-scope: growthepie snapshot/manifest, deterministic processed panel build, and refreshed golden sample.
`src/etl/growthepie_fetch.py` now enforces the locked STR schema contract and protocol row-omission rule (rows emitted only when both `l2_fees_eth` and `rent_paid_eth` exist).
`make gate` remains blocked by pre-existing processed-manifest outputs outside this task's allowed paths.

## What changed / what exists now

- Files/paths:
- `src/etl/growthepie_fetch.py`
- `data/raw_manifest/growthepie_2026-02-06.json`
- `data/samples/growthepie/vendor_daily_rollup_panel_sample.csv`
- `data/processed/growthepie/vendor_daily_rollup_panel.csv` (rebuilt local artifact; untracked)
- `data/raw/growthepie/2026-02-06/` (raw snapshot; append-only, untracked)

- Outputs produced:
- Raw snapshot date: `2026-02-06`
- Processed rows emitted: `12750`
- Rows filtered for missing core STR fields: `1699`
- Golden sample rows: `213` (window `2024-02-20` to `2024-04-30`, rollups `arbitrum/base/optimism`)

## How to reproduce / verify

- Commands:
- `python src/etl/growthepie_fetch.py --run-date 2026-02-06 --write-raw-manifest`
- `python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-06 --end-date 2026-02-06 --out-processed data/processed/growthepie/vendor_daily_rollup_panel.csv`
- `python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-06 --end-date 2026-02-06 --out-processed /tmp/vendor_daily_rollup_panel_rebuild_v3.csv --write-sample --sample-out /tmp/vendor_daily_rollup_panel_sample_rebuild_v3.csv`
- `cmp -s data/processed/growthepie/vendor_daily_rollup_panel.csv /tmp/vendor_daily_rollup_panel_rebuild_v3.csv`
- `cmp -s data/samples/growthepie/vendor_daily_rollup_panel_sample.csv /tmp/vendor_daily_rollup_panel_sample_rebuild_v3.csv`
- `python src/validation/validate_vendor_panel.py --sample`
- `make gate`

- Expected results:
- Offline rebuild comparisons are byte-identical (`cmp` exit code `0` for both processed + sample).
- Sample validation exits `0`.
- `make gate` fails only on `processed_manifest_consistency` for missing outputs not owned by T030:
  - `data/processed/panels/daily_rollup_panel_v1_sample.csv`
  - `data/processed/onchain/rollup_costs_daily.csv`
  - `data/processed/onchain/rollup_costs_decomposition_daily.csv`

## Assumptions / risks

- Assumes canonical growthepie mapping rule remains `rollup_id == origin_key` for mapped rollups; script now hard-fails on violations.
- Historical growthepie backfills can change past values; committed golden sample is now pinned to the current snapshot-derived values.

## Open questions / next steps

- @human: allow generation of non-T030 `data/processed/*` outputs (outside T030 `allowed_paths`) to satisfy `processed_manifest_consistency`, or treat this gate failure as unrelated to T030 acceptance.
