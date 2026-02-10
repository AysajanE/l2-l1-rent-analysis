---
task_id: T030
title: "growthepie ETL: snapshot exports + create golden sample panel"
workstream: W1
role: Worker
priority: high
dependencies:
  - "T020"
  - "T081"
allowed_paths:
  - "src/etl/growthepie_fetch.py"
  - "data/raw/growthepie/"
  - "data/raw_manifest/growthepie_"
  - "data/processed/growthepie/"
  - "data/samples/growthepie/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/analysis/"
  - "src/validation/"
outputs:
  - "src/etl/growthepie_fetch.py"
  - "data/raw/growthepie/YYYY-MM-DD/..."
  - "data/raw_manifest/growthepie_YYYY-MM-DD.json"
  - "data/processed/growthepie/vendor_daily_rollup_panel.csv"
  - "data/samples/growthepie/vendor_daily_rollup_panel_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Need credentials"
  - "Source instability / breaking changes"
---

# Task T030 — growthepie ETL: snapshot exports + create golden sample panel

## Context

Per `docs/protocol.md`, growthepie exports are the **primary** source for the STR denominator (`L2Fees`) and a **secondary** candidate for vendor `rent_paid/profit` series.

This task builds a reproducible ETL that:
- snapshots raw growthepie exports (append-only),
- records provenance in `data/raw_manifest/`,
- produces a normalized “vendor daily rollup panel” CSV for local analysis,
- and commits a tiny golden sample CSV under `data/samples/` for deterministic tests.

## Inputs

- `docs/protocol.md` (read-only): primary metric units + source priority
- `contracts/schemas/panel_schema_str_v1.yaml` (read-only): expected fields for the STR panel
- `registry/rollup_registry_v1.csv` (read-only): deterministic `origin_key -> rollup_id` mapping (canonical rule: `rollup_id == origin_key` for growthepie-covered rollups; see `registry/README.md`)
- growthepie API:
  - `https://api.growthepie.com/v1/master.json`
  - `https://api.growthepie.com/v1/export/{metric_key}.json`

## Outputs

- ETL code: `src/etl/growthepie_fetch.py`
  - Must be the only place that performs network calls for growthepie.
  - Should support a `--run-date YYYY-MM-DD` argument to control snapshot folder naming.
  - Should fetch at least: master.json + the daily exports needed for STR (fees, rent_paid, profit, txcount), preferring ETH-native series when available.
- Raw snapshots (append-only; not committed): `data/raw/growthepie/<YYYY-MM-DD>/...`
- Provenance manifest (tracked): `data/raw_manifest/growthepie_<YYYY-MM-DD>.json`
  - Use `python scripts/make_raw_manifest.py ...` and ensure it includes file hashes and the exact repro command.
- Local processed artifact (not committed): `data/processed/growthepie/vendor_daily_rollup_panel.csv`
  - Minimal columns should align with the schema contract from T020 (date, rollup_id, fees/rent/profit, units explicit).
  - `rollup_id` must be mapped deterministically from growthepie `origin_key` via `registry/rollup_registry_v1.csv` (do not invent ad-hoc joins in W1).
- Golden sample (tracked): `data/samples/growthepie/vendor_daily_rollup_panel_sample.csv`
  - Must be tiny (seconds to load).
  - Choose a fixed, documented date range and a small rollup subset.
  - Prefer the repo’s canonical sample window and rollup subset (see `data/samples/README.md`) unless explicitly blocked.
  - Include the same columns as the processed panel (subset of rows only).

## Success Criteria

- [ ] Running the ETL writes a dated snapshot under `data/raw/growthepie/<run-date>/` without overwriting existing snapshots
- [ ] Manifest exists under `data/raw_manifest/` and validates via `make gate`
- [ ] Processed panel CSV is produced deterministically from the raw snapshot
- [ ] Processed panel schema is asserted (at minimum: required STR columns per `contracts/schemas/panel_schema_str_v1.yaml`; fail fast on missing/invalid columns)
- [ ] Golden sample CSV is committed and is stable (fixed date range + rollups documented in-file or in a small README next to it)
- [ ] `make gate` passes

## Validation / Commands

- `make gate`
- Example (replace placeholders):
  - `python src/etl/growthepie_fetch.py --run-date 2026-01-22`
  - `python scripts/make_raw_manifest.py growthepie data/raw/growthepie/2026-01-22 --as-of 2026-01-22 -- python src/etl/growthepie_fetch.py --run-date 2026-01-22`

## Status
- State: blocked
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-01-22: Task created (Planner) as first real W1 ETL vertical slice.


- 2026-02-06: Claimed by swarm runner; starting worker (branch: T030_growthepie_etl_snapshot_and_golden_sample).

- 2026-02-06: Worker completed T030-scoped outputs and ETL hardening:
  - Updated `src/etl/growthepie_fetch.py` to assert schema contract (`contracts/schemas/panel_schema_str_v1.yaml`), enforce protocol row omission (emit only rows with both `l2_fees_eth` and `rent_paid_eth`), and fail fast on missing metric-key series.
  - Wrote raw snapshot + manifest via:
    - `python src/etl/growthepie_fetch.py --run-date 2026-02-06 --write-raw-manifest`
    - Manifest: `data/raw_manifest/growthepie_2026-02-06.json`
  - Rebuilt processed panel deterministically from snapshot:
    - `python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-06 --end-date 2026-02-06 --out-processed data/processed/growthepie/vendor_daily_rollup_panel.csv`
  - Refreshed golden sample from the same snapshot and replaced tracked file:
    - `data/samples/growthepie/vendor_daily_rollup_panel_sample.csv`
    - Determinism check: rebuilt sample/processed files byte-identical on repeat offline run.
  - Validation:
    - `python src/validation/validate_vendor_panel.py --sample` -> exit 0
    - `make gate` -> fails only on `processed_manifest_consistency` for missing outputs outside T030 allowed paths:
      - `data/processed/panels/daily_rollup_panel_v1_sample.csv`
      - `data/processed/onchain/rollup_costs_daily.csv`
      - `data/processed/onchain/rollup_costs_decomposition_daily.csv`
  - @human: confirm whether worker may generate those non-T030 outputs (outside `allowed_paths`) or treat this branch-level gate failure as non-blocking for T030 completion.


- 2026-02-06: @human Judge blocked: gates_failed, path_ownership_violation. Review log: /Users/aeziz-local/Research/Projects-05-Ethereum Blockchain Economic Analysis/Causal Influence of L2 Scaling Solutions on Ethereum L1 Mainnet Congestion/L1-L2-causal-influence-analysis/wt-T030/data/tmp/swarm_logs/T030_20260206T172429Z_judge_review.txt

- 2026-02-10: Worker reran T030 ETL and gates on current worktree state.
  - Snapshot + manifest (append-only):
    - `python src/etl/growthepie_fetch.py --run-date 2026-02-10 --write-raw-manifest`
    - Created `data/raw/growthepie/2026-02-10/` and `data/raw_manifest/growthepie_2026-02-10.json`.
  - Deterministic offline rebuild checks:
    - `python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-10 --end-date 2026-02-10 --out-processed data/processed/growthepie/vendor_daily_rollup_panel.csv`
    - `python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-10 --end-date 2026-02-10 --out-processed /tmp/vendor_daily_rollup_panel_rebuild_t030.csv`
    - `cmp -s data/processed/growthepie/vendor_daily_rollup_panel.csv /tmp/vendor_daily_rollup_panel_rebuild_t030.csv` => identical.
    - Sample rebuild comparison:
      - `python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-10 --end-date 2026-02-10 --out-processed /tmp/vendor_daily_rollup_panel_rebuild_with_sample_t030.csv --write-sample --sample-out /tmp/vendor_daily_rollup_panel_sample_rebuild_t030.csv`
      - `cmp -s data/samples/growthepie/vendor_daily_rollup_panel_sample.csv /tmp/vendor_daily_rollup_panel_sample_rebuild_t030.csv` => identical (no sample update needed).
  - Gate run:
    - `make gate` fails only on `processed_manifest_consistency` for missing outputs outside T030 `allowed_paths`:
      - `data/processed/panels/daily_rollup_panel_v1_sample.csv`
      - `data/processed/onchain/rollup_costs_daily.csv`
      - `data/processed/onchain/rollup_costs_decomposition_daily.csv`
  - @human: T030 remains blocked by cross-task manifest outputs not owned by W1/T030; either permit worker to materialize these out-of-scope files or accept T030 as complete on in-scope criteria.


- 2026-02-10: @human Judge blocked: gates_failed, path_ownership_violation. Review log: /tmp/swarm-worktrees/wt-T030/data/tmp/swarm_logs/T030_20260210T002146Z_judge_review.txt
