---
task_id: T099
title: "Validation: universe coverage report (registry readiness + attribution coverage)"
workstream: W5
role: Worker
priority: medium
dependencies:
  - "T082"
  - "T088"
allowed_paths:
  - "src/validation/report_universe_coverage.py"
  - "reports/validation/universe_coverage.json"
  - "reports/validation/universe_coverage.md"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/etl/"
  - "data/raw/"
outputs:
  - "src/validation/report_universe_coverage.py"
  - "reports/validation/universe_coverage.json"
  - "reports/validation/universe_coverage.md"
gates:
  - "make gate"
stop_conditions:
  - "Missing required inputs"
  - "Need to reinterpret rollup inclusion criteria"
---

# Task T099 — Validation: universe coverage report (registry readiness + attribution coverage)

## Context

Before scaling full-panel runs, we need a small deterministic “coverage” report that answers:

1) **Registry readiness**: how much of the in-scope rollup universe has evidence-backed attribution hooks (batcher/poster addresses)?
2) **Attribution coverage (post‑Dencun)**: how much of L1 blob usage/spend is attributable to the in-scope rollups (vs missing/unattributed)?

This report is informational (no new thresholds invented). It makes “how complete are we?” explicit and reproducible.

## Inputs

- `docs/protocol.md` (read-only): Dencun boundary and blob definitions
- `registry/rollup_registry_v1.csv` (read-only; seeded by T081/T082)
- Processed on-chain outputs (read-only; produced by T088):
  - `data/processed/onchain/rollup_costs_daily.parquet`
  - `data/processed/onchain/rollup_costs_decomposition_daily.parquet`
- Processed L1 blocks (read-only; produced by T087B; needed for L1 total blob gas baseline):
  - `data/processed/l1/l1_blocks.parquet`
- Optional triangulation inputs (read-only; if present):
  - `data/processed/blobscan/blobscan_daily.parquet` (T084)

## Outputs

- `src/validation/report_universe_coverage.py`
  - Deterministic; no network calls.
  - Must support `--sample` mode (default) that reads from committed `data/samples/` inputs when available.
  - Must follow the repo validation CLI contract (`src/validation/AGENTS.md`):
    - exit codes: `0` pass, `2` fail (only for internal errors/inconsistencies), `3` missing required inputs/schema mismatch
    - strict JSON summary with keys: `ok`, `inputs`, `metrics`, `failures`
- `reports/validation/universe_coverage.json`
- `reports/validation/universe_coverage.md`

## Success Criteria

- [ ] Script emits a strict JSON report with:
  - registry metrics (in-scope rollup count, address coverage state counts, total address count)
  - attribution coverage metrics for post‑Dencun days, including:
    - `sum_rollup_blob_gas_used / l1_blob_gas_used` (daily + aggregate)
    - (if available) `sum_rollup_blob_fee_burn_eth` and its relation to total L1 blob burn proxy
  - clear pointers to gaps (e.g., rollups with `state=unknown`, dates where coverage drops)
- [ ] Script is deterministic and offline (no web calls)
- [ ] `make gate` passes

## Status
- State: active
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-02-05: Added per feedback “Medium-Priority Suggestions”: introduce an explicit universe coverage report task after registry seeding (T082) and on-chain attribution (T088).



- 2026-02-10: Claimed by swarm runner; starting worker (branch: T099_validation_universe_coverage_report).
