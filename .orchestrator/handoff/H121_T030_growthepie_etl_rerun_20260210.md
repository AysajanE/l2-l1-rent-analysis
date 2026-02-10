# Handoff H121 — T030 growthepie ETL rerun + gate status (2026-02-10)

## Summary
T030 was rerun end-to-end in-scope. The growthepie snapshot, raw manifest, and deterministic processed/sample rebuild checks succeeded. `make gate` still fails only on `processed_manifest_consistency` for non-T030 outputs owned by other tasks/workstreams, so task state remains `blocked` pending `@human` ownership decision.

## Files created/changed
- `data/raw/growthepie/2026-02-10/master.json` (new, append-only raw snapshot)
- `data/raw/growthepie/2026-02-10/export/fees.json` (new, append-only raw snapshot)
- `data/raw/growthepie/2026-02-10/export/rent_paid.json` (new, append-only raw snapshot)
- `data/raw/growthepie/2026-02-10/export/profit.json` (new, append-only raw snapshot)
- `data/raw/growthepie/2026-02-10/export/txcount.json` (new, append-only raw snapshot)
- `data/raw_manifest/growthepie_2026-02-10.json` (new)
- `data/processed/growthepie/vendor_daily_rollup_panel.csv` (rebuilt local artifact; untracked)
- `.orchestrator/backlog/T030_growthepie_etl_snapshot_and_golden_sample.md` (`## Status` + `## Notes / Decisions` updated)
- `.orchestrator/handoff/H121_T030_growthepie_etl_rerun_20260210.md` (this note)

## Reproduction commands
- `python src/etl/growthepie_fetch.py --run-date 2026-02-10 --write-raw-manifest`
- `python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-10 --end-date 2026-02-10 --out-processed data/processed/growthepie/vendor_daily_rollup_panel.csv`
- `python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-10 --end-date 2026-02-10 --out-processed /tmp/vendor_daily_rollup_panel_rebuild_t030.csv`
- `python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-10 --end-date 2026-02-10 --out-processed /tmp/vendor_daily_rollup_panel_rebuild_with_sample_t030.csv --write-sample --sample-out /tmp/vendor_daily_rollup_panel_sample_rebuild_t030.csv`
- `cmp -s data/processed/growthepie/vendor_daily_rollup_panel.csv /tmp/vendor_daily_rollup_panel_rebuild_t030.csv`
- `cmp -s data/samples/growthepie/vendor_daily_rollup_panel_sample.csv /tmp/vendor_daily_rollup_panel_sample_rebuild_t030.csv`
- `make gate`

## Gate/test commands and output summary
- `python src/etl/growthepie_fetch.py --run-date 2026-02-10 --write-raw-manifest`
  - Exit `0`; manifest written: `data/raw_manifest/growthepie_2026-02-10.json`
  - Panel build counts: `rows_emitted=12786`, `sample_rows=213`.
- Determinism checks:
  - Processed panel byte-compare: identical.
  - Sample byte-compare vs tracked sample: identical.
- `make gate`
  - Exit `2`.
  - All checks pass except `processed_manifest_consistency`.
  - Missing outputs reported (outside T030 ownership):
    - `data/processed/panels/daily_rollup_panel_v1_sample.csv`
    - `data/processed/onchain/rollup_costs_daily.csv`
    - `data/processed/onchain/rollup_costs_decomposition_daily.csv`

## Assumptions / limitations
- T030 `allowed_paths` does not permit creating/fixing `data/processed/panels/*` or `data/processed/onchain/*` outputs required by `processed_manifest_consistency`.
- Task cannot be fully gate-green in this branch without cross-task ownership override or upstream/downstream task artifacts.

## Required follow-up
- `@human`: decide one of:
  1. Permit T030 worker to materialize the three missing non-T030 processed outputs solely to satisfy branch-level gate, or
  2. Accept T030 as complete for in-scope deliverables and evaluate gate at integration stage where dependent outputs exist.
