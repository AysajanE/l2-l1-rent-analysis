---
task_id: T089
title: "Data product: build daily_rollup_panel (contract v1) + sample + manifest"
workstream: W9
role: Worker
priority: high
dependencies:
  - "T096"
  - "T020"
  - "T030"
  - "T088"
parallel_ok: false
allowed_paths:
  - "src/etl/panel_build_daily_rollup_panel_v1.py"
  - "data/processed/panels/"
  - "data/processed_manifest/daily_rollup_panel_"
  - "data/samples/panels/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "data/raw/"
outputs:
  - "src/etl/panel_build_daily_rollup_panel_v1.py"
  - "data/processed/panels/daily_rollup_panel_v1.csv"
  - "data/processed_manifest/daily_rollup_panel_v1_<YYYY-MM-DD>.json"
  - "data/processed_manifest/daily_rollup_panel_v1_sample_<YYYY-MM-DD>.json"
  - "data/samples/panels/daily_rollup_panel_v1_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Missing upstream processed inputs"
  - "Contract mismatch (block)"
---

# Task T089 — Data product: build daily_rollup_panel (contract v1) + sample + manifest

## Context

The protocol’s primary metric STR is computed from the analysis-ready daily rollup panel (`daily_rollup_panel`) whose minimum contract is locked in `contracts/schemas/panel_schema_str_v1.yaml` (T020).

This task assembles the **contract v1** panel by joining:
- growthepie `l2_fees_eth` (denominator; T030),
- on-chain computed `rent_paid_eth` (authoritative numerator; T088),
at the grain (`date_utc`, `rollup_id`), respecting the protocol missingness rule (emit rows iff both core fields are present).

## Inputs

- `contracts/schemas/panel_schema_str_v1.yaml` (read-only): required keys/fields
- Processed growthepie vendor panel from T030 (read-only)
- Processed on-chain rollup costs from T088 (read-only)

## Outputs

- Build script: `src/etl/panel_build_daily_rollup_panel_v1.py`
  - Deterministic; no network calls.
  - Writes outputs under `data/processed/panels/`.
- Panel dataset (not committed): `data/processed/panels/daily_rollup_panel_v1.csv`
- Processed manifests (tracked; append-only):
  - Sample-mode (default name in the reference script): `data/processed_manifest/daily_rollup_panel_v1_sample_<YYYY-MM-DD>.json`
  - Full-mode (default name in the reference script): `data/processed_manifest/daily_rollup_panel_v1_<YYYY-MM-DD>.json`
  - Must record input manifests + command + output hashes.
- Golden sample (tracked): `data/samples/panels/daily_rollup_panel_v1_sample.csv`
  - Small fixed window + subset of rollups; sufficient for deterministic tests/figures.
  - Prefer the repo’s canonical sample window + rollup subset (see `data/samples/README.md`) unless explicitly blocked.

## Success Criteria

- [ ] Output conforms to the v1 contract (keys + required fields + units)
- [ ] Missingness rule is implemented exactly as in `docs/protocol.md`
- [ ] Output schema is asserted against `contracts/schemas/panel_schema_str_v1.yaml` (fail fast on missing/invalid columns)
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` (append-only; includes input manifests + output hashes)
- [ ] Golden sample is committed and stable
- [ ] `make gate` passes

## Status
- State: active
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-01-30: Task created (Planner) to produce the canonical STR-ready dataset from authoritative sources.


- 2026-02-10: Claimed by swarm runner; starting worker (branch: T089_panel_build_daily_rollup_panel_v1).
