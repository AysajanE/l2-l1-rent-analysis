---
task_id: T081
title: "Registry: add source keys + in-scope flags to rollup registry"
workstream: W3
role: Worker
priority: high
dependencies:
  - "T020"
allowed_paths:
  - "registry/rollup_registry_v1.csv"
  - "registry/CHANGELOG.md"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "src/"
  - "data/raw/"
outputs:
  - "registry/rollup_registry_v1.csv"
  - "registry/CHANGELOG.md"
gates:
  - "make gate"
stop_conditions:
  - "Need to reinterpret rollup inclusion criteria"
  - "Ambiguous rollup identity requires @human"
---

# Task T081 — Registry: add source keys + in-scope flags to rollup registry

## Context

Full-scale ingestion and reconciliation require deterministic joins across sources (growthepie, L2BEAT, Blobscan/on-chain). The protocol lock requires a stable `rollup_id` join key, but ETL needs explicit mappings from each source’s identifier → `rollup_id`.

This task upgrades the registry so downstream ETL can map:
- growthepie `origin_key` → `rollup_id`
- L2BEAT project slug → `rollup_id`

and so the rollup universe can be time-varying and explicitly marked in-scope.

## Inputs

- `docs/protocol.md` (read-only): rollup inclusion criteria and time-window semantics
- `registry/rollup_registry_v1.csv` (existing canonical registry)
- growthepie `master.json` origins list (for candidate `origin_key` values)
- L2BEAT project list (for candidate slugs)

## Outputs

- `registry/rollup_registry_v1.csv`
  - Add columns as needed (prefer additive/backward-compatible):
    - `origin_key` (growthepie)
    - `l2beat_slug`
    - `in_scope` (boolean-ish; or encode via `status` + start/end date)
  - Populate mappings for all existing rows where known; leave blank only with an explicit note.
  - Ensure evidence links are present for any new mapping decisions.
- `registry/CHANGELOG.md`
  - Record:
    - what columns were added,
    - what mappings were populated,
    - expected impact on join coverage.

## Success Criteria

- [ ] Registry contains a deterministic mapping for growthepie + L2BEAT identifiers for the in-scope rollup universe
- [ ] Registry changes are recorded in `registry/CHANGELOG.md` with evidence where applicable
- [ ] `make gate` passes

## Status
- State: done
- Last updated: 2026-02-06
## Notes / Decisions

- 2026-01-30: Task created (Planner) to make source joins deterministic before scaling ETL.



- 2026-02-06: Planner reconciliation — outputs already exist in repo; moved state to ready_for_review to clear control-plane drift before unattended fullscale preflight.


- 2026-02-06: Judge approval — promoted to done after repo-level gate/test/preflight checks and output existence verification to unblock downstream dependencies.
