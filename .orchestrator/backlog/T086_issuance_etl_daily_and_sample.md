---
task_id: T086
title: "Issuance ETL: ingest daily ETH issuance series + golden sample"
workstream: W1
role: Worker
priority: medium
dependencies:
  - "T096"
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
  - "Definition ambiguity (issuance definition/source mismatch)"
  - "Need API credentials"
---

# Task T086 — Issuance ETL: ingest daily ETH issuance series + golden sample

## Context

For “burn vs issuance” style outputs and related interpretation, we need a daily ETH issuance series with documented provenance. There are multiple possible issuance definitions (consensus issuance, net issuance, supply change); this task must lock one and document it.

## Inputs

- Candidate issuance sources (choose one primary + one secondary tolerance check):
  - Ultrasound.money API
  - Beacon chain / protocol issuance datasets
  - Other reputable public datasets (must be cited in the task notes)

## Outputs

- ETL code: `src/etl/issuance_fetch.py`
- Raw snapshots (append-only): `data/raw/issuance/<YYYY-MM-DD>/...`
- Raw manifest (tracked): `data/raw_manifest/issuance_<YYYY-MM-DD>.json`
- Normalized issuance table (not committed): `data/processed/issuance/issuance_daily.parquet`
  - Include: `date_utc`, `issuance_eth` (and any additional fields only if clearly defined).
- Processed manifest (tracked): `data/processed_manifest/issuance_daily_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/issuance/issuance_daily_sample.csv`

## Success Criteria

- [ ] Issuance definition is explicit and reproducible from the chosen source
- [ ] Raw manifest exists and is append-only
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` and includes input manifests + output hashes
- [ ] Golden sample is committed and stable
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-02-04

## Notes / Decisions

- 2026-01-30: Task created (Planner); issuance is needed for “burn vs issuance” context and counterfactual framing.
