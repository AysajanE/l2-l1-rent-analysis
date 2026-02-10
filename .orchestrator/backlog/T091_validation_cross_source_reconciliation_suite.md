---
task_id: T091
title: "Validation: cross-source reconciliation (growthepie vs on-chain vs L2BEAT; Blobscan sanity)"
workstream: W5
role: Worker
priority: high
dependencies:
  - "T083"
  - "T084"
  - "T087B"
  - "T089"
gates:
  - "make gate"
stop_conditions:
  - "Validation failure beyond tolerance"
allowed_paths:
  - "src/validation/validate_cross_source.py"
  - "reports/validation/cross_source_validation.json"
  - "reports/validation/cross_source_validation.md"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/etl/"
  - "data/raw/"
outputs:
  - "src/validation/validate_cross_source.py"
  - "reports/validation/cross_source_validation.json"
  - "reports/validation/cross_source_validation.md"
---

# Task T091 — Validation: cross-source reconciliation (growthepie vs on-chain vs L2BEAT; Blobscan sanity)

## Context

Full-scale results require reconciliation across:
- growthepie (vendor series; primary for `L2Fees`, secondary for `rent_paid/profit`),
- on-chain computed rollup rent (authoritative for `RentPaid`),
- L2BEAT costs (triangulation),
- Blobscan aggregates (blob usage cross-checks).

This task implements deterministic validation scripts and emits both machine-readable JSON and a short human-facing report.

## Inputs

- `docs/protocol.md` (read-only): tolerances and regime definitions
- Processed tables produced by:
  - T083 (L2BEAT)
  - T084 (Blobscan)
  - T087B (L1 blocks table; on-chain blob gas used aggregates)
  - T089 (v1 daily_rollup_panel; includes on-chain rent + growthepie fees)

## Outputs

- `src/validation/validate_cross_source.py`
  - Deterministic; no network calls.
  - Should support:
    - `--sample` mode (uses committed samples if present)
    - `--full` mode (reads from `data/processed/`)
  - Must follow the repo validation CLI contract (`src/validation/AGENTS.md`):
    - exit codes: `0` pass, `2` fail (beyond tolerance), `3` missing required inputs/schema mismatch
    - strict JSON summary with keys: `ok`, `inputs`, `metrics`, `failures`
- `reports/validation/cross_source_validation.json`
  - Include pass/fail + key metrics:
    - monthly reconciliation deltas for top rollups
    - blobGasUsed tolerance check on a sample month (Blobscan vs on-chain extraction, if both available)
  - `failures[]` entries must include pointers to offending rows (date/rollup) where applicable.
- `reports/validation/cross_source_validation.md`
  - Summarize findings and the smallest next experiment if something fails.

## Success Criteria

- [ ] Validation respects protocol tolerances (no invented thresholds)
- [ ] Reports are deterministic and reproducible from local inputs only
- [ ] `make gate` passes

## Status
- State: done
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-01-30: Task created (Planner) to enforce “anti-dashboard-science” cross-source reconciliation before analysis.
- 2026-02-05: Added explicit dependency on T087B so Blobscan vs on-chain `blobGasUsed` checks can be run deterministically (block-header aggregates).


- 2026-02-10: Claimed by swarm runner; starting worker (branch: T091_validation_cross_source_reconciliation_suite).

- 2026-02-10: Implemented/updated `src/validation/validate_cross_source.py` to satisfy the validation CLI contract and task mode requirements:
  - `--sample` now auto-resolves committed sample inputs (with processed fallbacks) for growthepie/on-chain/L2BEAT and optional blob inputs.
  - `--full` now defaults to `data/processed/...` candidate inputs (instead of requiring explicit `--*-csv` arguments).
  - Added `.parquet` table loading support (pyarrow reader with CSV fallback for stdlib-only payloads).
  - Blob on-chain aggregation now uses per-day `max` when reading panel-style `l1_blob_gas_used` repeated per rollup row to avoid double counting.
- 2026-02-10: Generated required report artifacts:
  - `reports/validation/cross_source_validation.json`
  - `reports/validation/cross_source_validation.md`
  - Reproduction command: `python src/validation/validate_cross_source.py --sample`
- 2026-02-10: Validation outputs (sample mode):
  - Exit code `2` (beyond tolerance), `ok=false`.
  - Monthly reconciliation failures beyond 10%: 2 rows (`arbitrum`, `2024-04`, growthepie-vs-onchain and l2beat-vs-onchain).
  - Blobsanity check evaluated month `2024-04`: `days_compared=30`, `days_gt_1pct=30`.
  - `failures[]` includes row pointers (`month_utc`/`rollup_id` for monthly; `date_utc` for blob daily checks).
- 2026-02-10: Full-mode behavior check:
  - `python src/validation/validate_cross_source.py --full` returns exit `3` with missing required processed inputs in this worktree.
- 2026-02-10: Gates/tests run:
  - `make gate` -> pass
  - `make test` -> pass (`Ran 46 tests`, `OK`)
- 2026-02-10: Assumptions/limitations:
  - Current branch does not include `data/processed/...` tables required for full-mode reconciliation; full mode reports missing inputs as designed.
  - Sample-mode blob check uses `data/samples/panels/daily_rollup_panel_v2_sample.csv` as on-chain blob baseline when available.
- 2026-02-10: `@human` stop condition triggered (`Validation failure beyond tolerance`):
  - Monthly reconciliation exceeds 10% tolerance for `arbitrum` in `2024-04` (growthepie-vs-onchain and l2beat-vs-onchain).
  - Blobscan vs on-chain blobGasUsed exceeds 1% tolerance on 30/30 evaluated days in `2024-04`.
  - Smallest decision needed: confirm whether to treat current sample mismatches as expected fixture divergence (keep validator behavior) or require upstream sample/attribution alignment before unblocking W5/W6 downstream work.


- 2026-02-10: Judge: gates ok; ownership ok. Review log: /tmp/swarm-worktrees/wt-T091/data/tmp/swarm_logs/T091_20260210T110027Z_judge_review.txt
