---
task_id: T083
title: "L2BEAT ETL: ingest daily costs series + golden sample"
workstream: W1
role: Worker
priority: medium
dependencies:
  - "T096"
  - "T081"
parallel_ok: true
allowed_paths:
  - "src/etl/l2beat_fetch.py"
  - "data/raw/l2beat/"
  - "data/raw_manifest/l2beat_"
  - "data/processed/l2beat/"
  - "data/processed_manifest/l2beat_"
  - "data/samples/l2beat/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/analysis/"
  - "src/validation/"
outputs:
  - "src/etl/l2beat_fetch.py"
  - "data/raw/l2beat/YYYY-MM-DD/..."
  - "data/raw_manifest/l2beat_YYYY-MM-DD.json"
  - "data/processed/l2beat/l2beat_costs_daily.parquet"
  - "data/processed_manifest/l2beat_costs_daily_YYYY-MM-DD.json"
  - "data/samples/l2beat/l2beat_costs_daily_sample.csv"
  - "data/samples/l2beat/README.md"
gates:
  - "make gate"
stop_conditions:
  - "No stable L2BEAT endpoint discovered"
  - "Source instability / breaking changes"
---

# Task T083 — L2BEAT ETL: ingest daily costs series + golden sample

## Context

Per `docs/protocol.md`, L2BEAT costs are a **triangulation** source (sanity check) for rent paid. This task builds a reproducible ETL that:
- discovers a stable data endpoint (preferred) or implements a robust fallback **without browser DevTools** (curlable discovery),
- snapshots raw responses (append-only),
- writes a normalized daily costs table, and
- commits a small golden sample for deterministic validation/reconciliation tests.

This task depends on T081 so the registry can provide a deterministic `l2beat_slug -> rollup_id` mapping.

## Inputs

- `registry/rollup_registry_v1.csv` (read-only): `l2beat_slug` mappings
- L2BEAT costs page / endpoints: `https://l2beat.com/scaling/costs`
- `docs/protocol.md` (read-only): cross-source tolerances and definitions
- `data/samples/l2beat/README.md` (read-only starter): swarm-friendly endpoint discovery notes and schema snapshot policy

## Outputs

- ETL code: `src/etl/l2beat_fetch.py`
  - Must support `--run-date YYYY-MM-DD` for snapshot folder naming.
  - Must write raw snapshots to a dated folder and never overwrite.
  - Must record reproduction details in `data/raw_manifest/`.
  - Must support a curlable discovery path (no interactive browser): `python src/etl/l2beat_fetch.py --discover`.
- Raw snapshots (append-only; not committed): `data/raw/l2beat/<YYYY-MM-DD>/...`
- Raw manifest (tracked): `data/raw_manifest/l2beat_<YYYY-MM-DD>.json`
- Normalized daily table (not committed): `data/processed/l2beat/l2beat_costs_daily.parquet`
  - Include at minimum: `date_utc`, `rollup_id`, `l2beat_slug`, `total_cost_eth`, `total_cost_usd`.
- Processed manifest (tracked): `data/processed_manifest/l2beat_costs_daily_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/l2beat/l2beat_costs_daily_sample.csv`
  - Small fixed window and a small rollup subset; document the choice in-file or adjacent README.
  - Prefer the repo’s canonical sample window + rollup subset (see `data/samples/README.md`) unless explicitly blocked.
- Endpoint discovery + schema snapshot notes (tracked): `data/samples/l2beat/README.md`
  - Must include endpoint(s), request parameters, and a high-level response schema snapshot.
  - Update if L2BEAT changes their API/procedure names so swarm runs remain deterministic.

## Success Criteria

- [ ] Raw snapshot is written to a dated folder (append-only)
- [ ] Raw manifest exists and validates via `make gate`
- [ ] Normalized daily table is reproducible from the raw snapshot
- [ ] Normalized table schema is asserted (required columns at minimum: `date_utc`, `rollup_id`, `l2beat_slug`, `total_cost_eth`, `total_cost_usd`; fail fast on missing/invalid columns)
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` and includes input manifests + output hashes
- [ ] Golden sample is committed and stable
- [ ] `data/samples/l2beat/README.md` captures curlable discovery + response schema snapshot (no DevTools dependency)
- [ ] `make gate` passes

## Status
- State: done
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-01-30: Task created (Planner) to enable cross-source rent triangulation at scale.


- 2026-02-10: Claimed by swarm runner; starting worker (branch: T083_l2beat_etl_costs_daily_and_sample).

- 2026-02-10: Implemented full ETL in `src/etl/l2beat_fetch.py` with:
  - `--discover` curlable endpoint discovery,
  - `--mode full` to snapshot raw L2BEAT tRPC responses, normalize daily costs, assert required schema columns, write parquet output, and optionally write manifests + sample,
  - append-only snapshot behavior with resume support (reuses existing raw files for same run-date instead of overwriting).

- 2026-02-10: Generated task outputs using:
  - `PYTHONPATH=/tmp/pydeps python src/etl/l2beat_fetch.py --run-date 2026-02-10 --start-date 2022-01-01 --end-date 2026-02-10 --filter-type rollups --write-raw-manifest --write-processed-manifest --write-sample`
  - Artifacts:
    - `data/raw/l2beat/2026-02-10/...` (table + project charts),
    - `data/raw_manifest/l2beat_2026-02-10.json`,
    - `data/processed/l2beat/l2beat_costs_daily.parquet`,
    - `data/processed_manifest/l2beat_costs_daily_2026-02-10.json`,
    - `data/samples/l2beat/l2beat_costs_daily_sample.csv`,
    - `data/samples/l2beat/README.md` updated with canonical command + schema index mapping.

- 2026-02-10: Gate/test runs:
  - `make test` passed.
  - `make gate` failed on pre-existing unrelated processed manifests requiring missing files under:
    - `data/processed/onchain/...`
    - `data/processed/panels/...`
  - Those paths are outside this task's `allowed_paths`; cannot remediate within T083 scope. `@human` needed to unblock gate strategy in this environment/worktree.


- 2026-02-10: Judge: gates ok; ownership ok. Review log: /tmp/swarm-worktrees/wt-T083/data/tmp/swarm_logs/T083_20260210T003111Z_judge_review.txt
