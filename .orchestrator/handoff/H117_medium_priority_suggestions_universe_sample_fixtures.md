# Handoff H117 — Medium-priority suggestions: coverage task + sample window + fee-math fixtures

## Summary (1–3 sentences)

Implemented the “Nice to Have” medium-priority feedback by (1) adding a universe coverage report task (post-registry + post-attribution), (2) standardizing a canonical sample window across sources, and (3) adding a future task to lock fee-component math via deterministic blob-tx fixtures once L1 samples exist.

## What changed / what exists now

- Files/paths:
  - `.orchestrator/backlog/T099_validation_universe_coverage_report.md`: new W5 task for registry readiness + post‑Dencun attribution coverage reporting.
  - `.orchestrator/backlog/T100_onchain_fee_component_fixtures_blob_tx.md`: new W2 task for deterministic fee-component fixtures + offline self-test (blob tx included).
  - `data/samples/README.md`: defines the canonical sample window and rollup subset used by sample-mode outputs.
  - `data/samples/*/README.md`: now reference the canonical sample window for alignment.
  - `data/samples/panels/daily_rollup_panel_v1_sample.csv`: extended to cover the canonical window through `2024-04-30` (UTC).
  - Updated task specs to reference the canonical sample window where they produce golden samples (T030/T083/T084/T085/T086/T087B/T087C/T088/T089/T090).

## How to reproduce / verify

- Commands:
  - `make gate`
- Expected results:
  - `task_hygiene` / `task_dependencies` remain green after new tasks are added.
  - No CI/network calls are introduced; changes are doc/task + sample artifacts only.

## Assumptions / risks

- The canonical window is designed for cross-source sample-mode alignment; heavy on-chain extraction samples may remain sparse within it (documented in `data/samples/README.md`).
- The extended panel sample is a deterministic golden sample (not a claim of ground-truth data); downstream tasks should still source authoritative series from ETL outputs.

## Open questions / next steps

- When T087B/T087C commit real on-chain samples, implement T100 to produce blob-tx fee-component fixtures and a self-test script that guards integer-safe computations.
- Implement T099 after T088 to quantify post‑Dencun attribution coverage (blob gas/share) and surface registry gaps early.

