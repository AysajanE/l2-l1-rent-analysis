# Handoff H123 — T030 rerun (snapshot 2026-02-09) and gate status

## Summary
T030 was rerun end-to-end in-scope on 2026-02-10 with a fresh append-only snapshot folder (`2026-02-09`) and manifest. Processed/sample determinism checks passed again. `make gate` still fails only on out-of-scope processed outputs owned by other workstreams.

## What changed / what exists now

- Files/paths:
  - `data/raw/growthepie/2026-02-09/master.json`
  - `data/raw/growthepie/2026-02-09/export/fees.json`
  - `data/raw/growthepie/2026-02-09/export/rent_paid.json`
  - `data/raw/growthepie/2026-02-09/export/profit.json`
  - `data/raw/growthepie/2026-02-09/export/txcount.json`
  - `data/raw_manifest/growthepie_2026-02-09.json`
  - `data/processed/growthepie/vendor_daily_rollup_panel.csv` (local rebuild; untracked)
  - `.orchestrator/backlog/T030_growthepie_etl_snapshot_and_golden_sample.md` (`## Notes / Decisions` appended)
  - `.orchestrator/handoff/H123_T030_growthepie_etl_rerun_20260210_snapshot_20260209.md`
- Outputs produced:
  - Panel rows emitted: `12798`
  - Sample rows emitted: `213`

## How to reproduce / verify

- Commands:
  - `python src/etl/growthepie_fetch.py --run-date 2026-02-09 --write-raw-manifest`
  - `python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-09 --end-date 2026-02-09 --out-processed /tmp/vendor_daily_rollup_panel_rebuild_t030_20260209.csv`
  - `cmp -s data/processed/growthepie/vendor_daily_rollup_panel.csv /tmp/vendor_daily_rollup_panel_rebuild_t030_20260209.csv`
  - `python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-09 --end-date 2026-02-09 --out-processed /tmp/vendor_daily_rollup_panel_rebuild_with_sample_t030_20260209.csv --write-sample --sample-out /tmp/vendor_daily_rollup_panel_sample_rebuild_t030_20260209.csv`
  - `cmp -s data/samples/growthepie/vendor_daily_rollup_panel_sample.csv /tmp/vendor_daily_rollup_panel_sample_rebuild_t030_20260209.csv`
  - `python src/validation/validate_vendor_panel.py --sample`
  - `make gate`
- Expected results:
  - Both `cmp` commands exit `0` (byte-identical rebuilds).
  - `validate_vendor_panel.py --sample` exits `0`.
  - `make gate` exits non-zero only on `processed_manifest_consistency` with missing output files:
    - `data/processed/panels/daily_rollup_panel_v1_sample.csv`
    - `data/processed/onchain/rollup_costs_daily.csv`
    - `data/processed/onchain/rollup_costs_decomposition_daily.csv`

## Assumptions / risks
- T030 `allowed_paths` does not include `data/processed/panels/` or `data/processed/onchain/`; creating those files would violate path ownership.
- Gate remains branch-blocked until dependent W2/W9 outputs are present or ownership is explicitly overridden.

## Open questions / next steps
- `@human`: choose one:
  1. Grant temporary path override for this worker to materialize the three missing processed outputs.
  2. Keep T030 blocked and route gate repair to W2/W9 owners, then rerun `make gate`.
