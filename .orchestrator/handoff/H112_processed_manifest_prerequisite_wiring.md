# Handoff H112 — Wire processed-manifest helper as a prerequisite (T096)

## Summary (1–3 sentences)

Updated all tasks that emit `data/processed_manifest/*` to explicitly depend on T096 and to require using the standardized helper `scripts/make_processed_manifest.py`. Added a quality-gate rule so future processed-manifest–emitting tasks cannot omit the T096 dependency.

## What changed / what exists now

- Files/paths:
  - `.orchestrator/backlog/T083_l2beat_etl_costs_daily_and_sample.md`: add `dependencies: ["T096", ...]` + success criterion for helper-generated processed manifest.
  - `.orchestrator/backlog/T084_blobscan_etl_blob_daily_and_sample.md`: add `dependencies: ["T096"]` + success criterion.
  - `.orchestrator/backlog/T085_prices_etl_eth_usd_daily_and_sample.md`: add `dependencies: ["T096"]` + success criterion.
  - `.orchestrator/backlog/T086_issuance_etl_daily_and_sample.md`: add `dependencies: ["T096"]` + success criterion.
  - `.orchestrator/backlog/T087_onchain_etl_l1_raw_extract_headers_txs_receipts.md`: add `dependencies: ["T096"]` + success criterion.
  - `.orchestrator/backlog/T088_onchain_compute_rollup_daily_costs_and_decomposition.md`: add `dependencies: ["T096", ...]` + success criterion.
  - `.orchestrator/backlog/T089_panel_build_daily_rollup_panel_v1.md`: add `dependencies: ["T096", ...]` + success criterion.
  - `.orchestrator/backlog/T090_panel_build_daily_rollup_panel_v2_enriched.md`: add `dependencies: ["T096", ...]` + success criterion.
  - `scripts/quality_gates.py`: enforce “tasks emitting `data/processed_manifest/*` must depend on T096”.
- Outputs produced:
  - No new datasets; this is control-plane wiring + a new dependency guardrail in `make gate`.

## How to reproduce / verify

- Commands:
  - `make gate`
  - `make test`
- Expected results:
  - `make gate` passes with `[task_dependencies] ok=True ...`
  - If a task declares an output under `data/processed_manifest/` but omits `T096` from `dependencies`, `make gate` fails with `missing_dependency:T096_for_processed_manifest`.

## Assumptions / risks

- Assumes `scripts/make_processed_manifest.py` is the canonical generator for `data/processed_manifest/*` and remains offline/deterministic.
- This does not enforce that workers actually *run* the helper during ETL; it enforces the dependency wiring and success-criteria clarity. (Enforcement of manifest *contents* can be added later if needed.)

## Open questions / next steps

- Consider adding a processed-manifest validity gate (schema_version/required keys) once more sample manifests are committed.
