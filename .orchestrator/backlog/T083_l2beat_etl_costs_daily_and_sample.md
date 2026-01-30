---
task_id: T083
title: "L2BEAT ETL: ingest daily costs series + golden sample"
workstream: W1
role: Worker
priority: medium
dependencies:
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
gates:
  - "make gate"
stop_conditions:
  - "No stable L2BEAT endpoint discovered"
  - "Source instability / breaking changes"
---

# Task T083 — L2BEAT ETL: ingest daily costs series + golden sample

## Context

Per `docs/protocol.md`, L2BEAT costs are a **triangulation** source (sanity check) for rent paid. This task builds a reproducible ETL that:
- discovers a stable data endpoint (preferred) or implements a robust fallback,
- snapshots raw responses (append-only),
- writes a normalized daily costs table, and
- commits a small golden sample for deterministic validation/reconciliation tests.

This task depends on T081 so the registry can provide a deterministic `l2beat_slug -> rollup_id` mapping.

## Inputs

- `registry/rollup_registry_v1.csv` (read-only): `l2beat_slug` mappings
- L2BEAT costs page / endpoints: `https://l2beat.com/scaling/costs`
- `docs/protocol.md` (read-only): cross-source tolerances and definitions

## Outputs

- ETL code: `src/etl/l2beat_fetch.py`
  - Must support `--run-date YYYY-MM-DD` for snapshot folder naming.
  - Must write raw snapshots to a dated folder and never overwrite.
  - Must record reproduction details in `data/raw_manifest/`.
- Raw snapshots (append-only; not committed): `data/raw/l2beat/<YYYY-MM-DD>/...`
- Raw manifest (tracked): `data/raw_manifest/l2beat_<YYYY-MM-DD>.json`
- Normalized daily table (not committed): `data/processed/l2beat/l2beat_costs_daily.parquet`
  - Include at minimum: `date_utc`, `rollup_id`, `l2beat_slug`, `total_cost_eth`, `total_cost_usd`.
- Processed manifest (tracked): `data/processed_manifest/l2beat_costs_daily_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/l2beat/l2beat_costs_daily_sample.csv`
  - Small fixed window and a small rollup subset; document the choice in-file or adjacent README.

## Success Criteria

- [ ] Raw snapshot is written to a dated folder (append-only)
- [ ] Raw manifest exists and validates via `make gate`
- [ ] Normalized daily table is reproducible from the raw snapshot
- [ ] Golden sample is committed and stable
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-01-30

## Notes / Decisions

- 2026-01-30: Task created (Planner) to enable cross-source rent triangulation at scale.

