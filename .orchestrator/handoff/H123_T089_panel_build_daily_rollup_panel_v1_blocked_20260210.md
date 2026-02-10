# Handoff H123 — T089 daily_rollup_panel_v1 build (sample complete, full-mode blocked)

## Summary
T089 now has a deterministic v1 panel builder that joins growthepie fees with on-chain rent in both full and sample join modes. The tracked v1 sample panel and a new sample processed manifest (`2026-02-10`) were rebuilt successfully. Full-mode output remains blocked by missing upstream processed inputs required by task stop conditions.

## What changed / what exists now
- Files/paths:
  - `src/etl/panel_build_daily_rollup_panel_v1.py`
    - `--sample` now joins canonical sample source files instead of reading `data/samples/panels/daily_rollup_panel_v1_sample.csv` as input.
    - Added `--write-sample` and `--sample-out` for deterministic sample refresh.
    - Manifest wiring now records join inputs and includes sample output when written.
  - `data/samples/panels/daily_rollup_panel_v1_sample.csv` (updated)
  - `data/processed_manifest/daily_rollup_panel_v1_sample_2026-02-10.json` (new)
  - `.orchestrator/backlog/T089_panel_build_daily_rollup_panel_v1.md` (`## Status` + `## Notes / Decisions` only)
  - `.orchestrator/handoff/H123_T089_panel_build_daily_rollup_panel_v1_blocked_20260210.md` (this note)
- Outputs produced:
  - Sample-mode panel rows: 213
  - Sample manifest includes input manifests:
    - `data/raw_manifest/growthepie_2026-02-10.json`
    - `data/processed_manifest/onchain_rollup_costs_2026-02-06.json`

## How to reproduce / verify
- Commands:
  - `python src/etl/panel_build_daily_rollup_panel_v1.py --sample --write-sample --write-manifest --as-of 2026-02-10 --manifest-inputs data/raw_manifest/growthepie_2026-02-10.json data/processed_manifest/onchain_rollup_costs_2026-02-06.json`
  - `python src/etl/panel_build_daily_rollup_panel_v1.py --fees-csv data/processed/growthepie/vendor_daily_rollup_panel.csv --rent-csv data/processed/onchain/rollup_costs_daily.csv --write-manifest --as-of 2026-02-10 --manifest-inputs data/raw_manifest/growthepie_2026-02-10.json data/processed_manifest/onchain_rollup_costs_2026-02-06.json`
  - `make gate`
  - `make test`
- Expected results:
  - First command exits `0` and writes:
    - `data/samples/panels/daily_rollup_panel_v1_sample.csv`
    - `data/processed_manifest/daily_rollup_panel_v1_sample_2026-02-10.json`
  - Second command exits non-zero with missing input error until upstream processed inputs exist.
  - `make gate` passes.
  - `make test` passes (`Ran 42 tests`).

## Assumptions / risks
- Stop condition `Missing upstream processed inputs` is active for full-mode artifacts:
  - `data/processed/growthepie/vendor_daily_rollup_panel.csv`
  - `data/processed/onchain/rollup_costs_daily.csv`
- Git metadata is unavailable in this sandbox worktree (`.git` points to a missing external worktree path), so a local commit hash could not be captured for this run.

## Open questions / next steps
- `@human`: unblock T089 by providing or regenerating the two upstream processed inputs above in-branch, then run full-mode build to produce:
  - `data/processed/panels/daily_rollup_panel_v1.csv` (local, untracked)
  - `data/processed_manifest/daily_rollup_panel_v1_<YYYY-MM-DD>.json` (tracked)
