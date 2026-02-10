# Handoff H124 — T090 panel_build_daily_rollup_panel_v2 (sample complete, full-mode blocked)

## Summary (1–3 sentences)
Implemented contract-v2 panel builder hardening in `src/etl/panel_build_daily_rollup_panel_v2.py` with explicit deterministic join semantics, schema assertions, CSV/parquet-path input handling, and processed-manifest generation. Rebuilt sample-mode outputs and wrote a new sample processed manifest. Full-mode deliverables remain blocked by missing upstream processed inputs in this worktree.

## What changed / what exists now

- Files/paths:
- `src/etl/panel_build_daily_rollup_panel_v2.py`
- `data/processed_manifest/daily_rollup_panel_v2_sample_2026-02-10.json`
- `.orchestrator/backlog/T090_panel_build_daily_rollup_panel_v2_enriched.md` (`## Status` + `## Notes / Decisions` only)
- `.orchestrator/handoff/H124_T090_panel_build_daily_rollup_panel_v2_blocked_20260210.md`

- Outputs produced:
- Runtime output (untracked): `data/processed/panels/daily_rollup_panel_v2_sample.csv`
- Tracked manifest: `data/processed_manifest/daily_rollup_panel_v2_sample_2026-02-10.json`
- Tracked sample: `data/samples/panels/daily_rollup_panel_v2_sample.csv` rewritten deterministically with no content drift.

## How to reproduce / verify

- Commands:
- `python src/etl/panel_build_daily_rollup_panel_v2.py --sample --write-sample --write-manifest --as-of 2026-02-10 --manifest-inputs data/processed_manifest/daily_rollup_panel_v1_sample_2026-02-10.json data/processed_manifest/blobscan_daily_2026-02-10.json data/processed_manifest/prices_daily_2026-02-10.json data/processed_manifest/issuance_daily_2026-02-10.json`
- `python src/etl/panel_build_daily_rollup_panel_v2.py --panel-v1-csv data/processed/panels/daily_rollup_panel_v1.parquet --decomposition-csv data/processed/onchain/rollup_costs_decomposition_daily.csv --l1-regime-csv data/processed/blobscan/blobscan_daily.parquet --prices-csv data/processed/prices/prices_daily.parquet --issuance-csv data/processed/issuance/issuance_daily.parquet --out data/processed/panels/daily_rollup_panel_v2.parquet`
- `make gate`
- `make test`

- Expected results:
- First command exits `0` and writes sample processed output + `data/processed_manifest/daily_rollup_panel_v2_sample_2026-02-10.json`.
- Second command exits non-zero until upstream `data/processed/*` inputs exist.
- `make gate` passes.
- `make test` passes (`Ran 46 tests`, `OK`).

## Assumptions / risks

- In this worktree, full-mode inputs required by T090 are missing under `data/processed/`.
- Builder currently writes CSV payloads; `.parquet` paths are supported as filenames for stdlib-only portability unless pyarrow-backed parquet IO is explicitly added in scope.
- Sandbox git metadata is unavailable (`.git` points to an inaccessible external worktree path), so generated manifest `transform.git_sha` is `null`.

## Open questions / next steps

- `@human`: provide/regenerate these upstream processed inputs (or approve alternate full-mode paths) to unblock full outputs:
- `data/processed/panels/daily_rollup_panel_v1.parquet` (or compatible v1 input path)
- `data/processed/onchain/rollup_costs_decomposition_daily.csv`
- `data/processed/blobscan/blobscan_daily.parquet`
- `data/processed/prices/prices_daily.parquet`
- `data/processed/issuance/issuance_daily.parquet`
