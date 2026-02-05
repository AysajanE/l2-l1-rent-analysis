---
task_id: T086
title: "Issuance ETL: ingest daily ETH issuance series + golden sample"
workstream: W1
role: Worker
priority: medium
dependencies:
  - "T096"
  - "T097"
parallel_ok: true
allowed_paths:
  - "src/etl/issuance_fetch.py"
  - "data/raw/issuance/"
  - "data/raw_manifest/issuance_"
  - "data/processed/issuance/"
  - "data/processed_manifest/issuance_"
  - "data/samples/issuance/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/analysis/"
  - "src/validation/"
outputs:
  - "src/etl/issuance_fetch.py"
  - "data/raw/issuance/YYYY-MM-DD/..."
  - "data/raw_manifest/issuance_YYYY-MM-DD.json"
  - "data/processed/issuance/issuance_daily.parquet"
  - "data/processed_manifest/issuance_daily_YYYY-MM-DD.json"
  - "data/samples/issuance/issuance_daily_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Need API credentials"
---

# Task T086 — Issuance ETL: ingest daily ETH issuance series + golden sample

## Context

For “burn vs issuance” style outputs and related interpretation, we need a daily ETH issuance series with documented provenance.

**Issuance definition is locked in W0** (see T097 + `contracts/schemas/issuance_daily_v1.yaml` + `contracts/decisions.md`); this W1 task must implement the ETL deterministically against that contract (no new definition choices here).

## Inputs

- Locked definition + schema (read-only):
  - `docs/protocol.md` (issuance definition + source policy)
  - `contracts/schemas/issuance_daily_v1.yaml`
  - `contracts/decisions.md` (issuance decision entry)
- Sources (per W0 decision; do not substitute without `@human`):
  - Primary: `ultrasound.money` daily issuance series (snapshotted)
  - Secondary: beacon-chain explorer / consensus feed for tolerance checks

## Outputs

- ETL code: `src/etl/issuance_fetch.py`
- Raw snapshots (append-only): `data/raw/issuance/<YYYY-MM-DD>/...`
- Raw manifest (tracked): `data/raw_manifest/issuance_<YYYY-MM-DD>.json`
- Normalized issuance table (not committed): `data/processed/issuance/issuance_daily.parquet`
  - Must conform to `contracts/schemas/issuance_daily_v1.yaml` (include `date_utc`, `issuance_eth`, `source`, optional `method`).
- Processed manifest (tracked): `data/processed_manifest/issuance_daily_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/issuance/issuance_daily_sample.csv`
  - Prefer the repo’s canonical sample window (see `data/samples/README.md`) so the enriched panel v2 sample can join deterministically.

## Success Criteria

- [ ] Output conforms to `contracts/schemas/issuance_daily_v1.yaml` (daily UTC grain; `issuance_eth` in ETH; `source` set consistently)
- [ ] Raw manifest exists and is append-only
- [ ] Normalized table schema is asserted against `contracts/schemas/issuance_daily_v1.yaml` (fail fast on missing/invalid columns)
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` and includes input manifests + output hashes
- [ ] Golden sample is committed and stable
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-02-05

## Notes / Decisions

- 2026-01-30: Task created (Planner); issuance is needed for “burn vs issuance” context and counterfactual framing.
- 2026-02-05: Wired dependency on W0 issuance-definition lock (T097); W1 ETL must implement the locked `issuance_daily_v1` contract.
