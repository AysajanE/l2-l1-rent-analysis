# Handoff H116 — High-priority improvements A–D (task interface hardening)

## Summary (1–3 sentences)

Applied expert feedback “High-Priority Improvements (Should Fix)” items A–D by hardening task interfaces: explicit rollup_id mapping dependency, deterministic validation CLI contract, swarm-friendly L2BEAT discovery documentation, and integer-safe blob fee unit requirements.

## What changed / what exists now

- Files/paths:
  - `.orchestrator/backlog/T030_growthepie_etl_snapshot_and_golden_sample.md`: now depends on `T081` and explicitly requires deterministic `origin_key -> rollup_id` mapping via the registry.
  - `.orchestrator/backlog/T050_validation_vendor_panel_checks.md` and `.orchestrator/backlog/T091_validation_cross_source_reconciliation_suite.md`: explicitly require the validation CLI contract (exit codes + strict JSON schema) from `src/validation/AGENTS.md`.
  - `.orchestrator/backlog/T083_l2beat_etl_costs_daily_and_sample.md`: explicitly requires curlable discovery and maintaining `data/samples/l2beat/README.md`.
  - `.orchestrator/backlog/T084_blobscan_etl_blob_daily_and_sample.md`: requires integer `l1_blob_base_fee_wei` (canonical) and treats any gwei field as presentation-only.
  - `.orchestrator/backlog/T088_onchain_compute_rollup_daily_costs_and_decomposition.md`: requires emitting integer-safe wei component columns in decomposition outputs.
  - `.orchestrator/backlog/T080_contracts_lock_enriched_panel_schema_v2.md`: makes the integer-safe blob fee regime input requirements explicit in the v2 contract lock task.
- Outputs produced:
  - No new datasets; this is task/interface guidance and drift-prevention.

## How to reproduce / verify

- Commands:
  - `make gate`
- Expected results:
  - `task_dependencies` and `task_hygiene` pass with updated dependency wiring and task metadata.

## Assumptions / risks

- L2BEAT/Blobscan APIs can change. The tasks now require updating the sample README(s) and keeping discovery curlable; workers should block with `@human` if no stable public endpoint exists.
- rollup_id convention assumes growthepie chain keys can be used as canonical slugs for in-scope rollups; if growthepie changes identifiers, update `registry/rollup_registry_v1.csv` and log in `registry/CHANGELOG.md`.

## Open questions / next steps

- When implementing T084 ingestion, ensure the processed table uses integer wei for `l1_blob_base_fee_wei` and that any gwei presentation is derived at report time.
- For T091 implementation, reuse `src/validation/reporting.py` helpers to standardize JSON outputs and exit codes.

