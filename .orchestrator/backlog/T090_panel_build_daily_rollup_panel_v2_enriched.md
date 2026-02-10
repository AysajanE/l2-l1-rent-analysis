---
task_id: T090
title: "Data product: build enriched daily panel (contract v2) + sample + manifest"
workstream: W9
role: Worker
priority: medium
dependencies:
  - "T096"
  - "T080"
  - "T084"
  - "T085"
  - "T086"
  - "T089"
parallel_ok: false
allowed_paths:
  - "src/etl/panel_build_daily_rollup_panel_v2.py"
  - "data/processed/panels/"
  - "data/processed_manifest/daily_rollup_panel_"
  - "data/samples/panels/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "data/raw/"
outputs:
  - "src/etl/panel_build_daily_rollup_panel_v2.py"
  - "data/processed/panels/daily_rollup_panel_v2.parquet"
  - "data/processed_manifest/daily_rollup_panel_v2_YYYY-MM-DD.json"
  - "data/samples/panels/daily_rollup_panel_v2_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Missing upstream processed inputs"
  - "Contract mismatch (block)"
---

# Task T090 — Data product: build enriched daily panel (contract v2) + sample + manifest

## Context

Beyond the STR-minimum dataset (v1), full-scale research requires an enriched panel that includes regime variables and macro inputs. The enriched schema must be locked first (T080).

This task builds the **contract v2** panel by extending the v1 panel (T089) with:
- blob regime variables (T084),
- ETH/USD prices (T085),
- ETH issuance (T086),
and any other enrichment explicitly defined in the v2 contract.

## Inputs

- `contracts/schemas/panel_schema_str_v2.yaml` (read-only; produced by T080)
- `data/processed/panels/daily_rollup_panel_v1.parquet` (read-only; produced by T089)
- Processed blobscan, prices, issuance tables from T084/T085/T086 (read-only)

## Outputs

- Build script: `src/etl/panel_build_daily_rollup_panel_v2.py`
  - Deterministic; no network calls.
- Enriched panel (not committed): `data/processed/panels/daily_rollup_panel_v2.parquet`
- Processed manifest (tracked): `data/processed_manifest/daily_rollup_panel_v2_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/panels/daily_rollup_panel_v2_sample.csv`
  - Prefer the repo’s canonical sample window + rollup subset (see `data/samples/README.md`) unless explicitly blocked.

## Success Criteria

- [ ] Output conforms to the v2 contract (field list + units + nullability)
- [ ] Output schema is asserted against `contracts/schemas/panel_schema_str_v2.yaml` (fail fast on missing/invalid columns)
- [ ] Join semantics are explicit and deterministic (document in code and manifest)
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` (append-only; includes input manifests + output hashes)
- [ ] Golden sample is committed and stable
- [ ] `make gate` passes

## Status
- State: active
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-01-30: Task created (Planner) to produce the enriched dataset used for regime + counterfactual analysis.


- 2026-02-10: Claimed by swarm runner; starting worker (branch: T090_panel_build_daily_rollup_panel_v2_enriched).
