# Handoff H091 — Cross-source reconciliation validation suite

## Summary (1-3 sentences)

Implemented and hardened `src/validation/validate_cross_source.py` to run deterministic cross-source reconciliation in both sample and full modes, with strict validation JSON output and contract exit codes. Generated the required validation artifacts under `reports/validation/`. Current sample run is intentionally failing tolerances (exit `2`) with actionable month/date pointers.

## Task metadata

- task_id: `T091`
- contract references:
  - `docs/protocol.md` (validation tolerances + source priority)
  - `src/validation/AGENTS.md` (validation CLI contract)
- timestamp_utc: `2026-02-10T10:58:58Z`
- git_commit: `unavailable` (git worktree metadata unavailable in this sandbox)
- reproduction command(s):
  - `python src/validation/validate_cross_source.py --sample`
  - `python src/validation/validate_cross_source.py --full`
- key inputs:
  - sample: `data/samples/growthepie/vendor_daily_rollup_panel_sample.csv`
  - sample: `data/samples/panels/daily_rollup_panel_v1_sample.csv`
  - sample: `data/samples/l2beat/l2beat_costs_daily_sample.csv`
  - sample optional blob: `data/samples/blobscan/blobscan_daily_sample.csv`
  - sample optional onchain blob: `data/samples/panels/daily_rollup_panel_v2_sample.csv`
- key outputs:
  - `reports/validation/cross_source_validation.json`
  - `reports/validation/cross_source_validation.md`

## What changed / what exists now

- Files/paths:
  - `src/validation/validate_cross_source.py`
  - `reports/validation/cross_source_validation.json`
  - `reports/validation/cross_source_validation.md`
  - `.orchestrator/backlog/T091_validation_cross_source_reconciliation_suite.md` (`## Status` + `## Notes / Decisions` only)
- Validator updates:
  - `--sample` auto-resolves committed sample inputs (with processed fallbacks).
  - `--full` now defaults to `data/processed/...` candidates.
  - Optional blob checks auto-run only when both blob sources are discoverable in default mode.
  - `.parquet` loading supported (pyarrow reader with CSV fallback).
  - On-chain blob daily aggregation uses per-day `max` for panel-style repeated `l1_blob_gas_used` fields.

## How to reproduce / verify

- Validation report generation:
  - `python src/validation/validate_cross_source.py --sample`
- Full-mode path resolution check:
  - `python src/validation/validate_cross_source.py --full`
- Required gates/tests:
  - `make gate`
  - `make test`

## Gate/test summary

- `python src/validation/validate_cross_source.py --sample` -> exit `2`
  - `monthly_reconciliation`: 2 rows above 10% tolerance (`arbitrum`, `2024-04`)
  - `blob_gas_used_reconciliation`: selected month `2024-04`, 30/30 days above 1%
- `python src/validation/validate_cross_source.py --full` -> exit `3`
  - missing required processed inputs in this worktree
- `make gate` -> pass
- `make test` -> pass (`Ran 46 tests`, `OK`)

## Assumptions / limitations

- Full-mode processed tables are not present in this branch (`data/processed/...`), so full mode correctly reports missing inputs.
- Sample-mode blob sanity relies on the committed panel v2 sample for daily on-chain blob baseline because the committed `l1_blocks_sample` is too sparse for a full month overlap with Blobscan sample.

## Open questions / next steps

- If a fresh `data/processed/l1/l1_blocks.*` and source tables are materialized in-branch, rerun `--full` and compare whether blob reconciliation remains above tolerance or narrows after aligned snapshot windows.
