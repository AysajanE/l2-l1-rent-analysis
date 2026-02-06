---
task_id: T082
title: "Registry: populate batcher addresses + evidence for top rollups"
workstream: W3
role: Worker
priority: medium
dependencies:
  - "T081"
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
  - "Missing credible evidence for an address mapping"
  - "Ambiguous attribution requires @human"
---

# Task T082 — Registry: populate batcher addresses + evidence for top rollups

## Context

On-chain rollup rent attribution (Phase 4) requires a set of rollup-associated L1 addresses and evidence. This repo’s starter registry includes `batcher_addresses_json`, but it must be populated and maintained with validity windows and citations.

This task focuses on **coverage for the top rollups** (by fees / prominence) so that on-chain attribution can start, even if long-tail rollups are incomplete.

## Inputs

- `registry/rollup_registry_v1.csv` (must already include required source keys from T081)
- Official rollup documentation / explorer labels / reputable sources for batcher/poster addresses
- (Optional) Blobscan/L2BEAT labels as supporting evidence (not sole evidence)

## Outputs

- `registry/rollup_registry_v1.csv`
  - Populate `batcher_addresses_json` for an initial target set (recommend: top 10–20 rollups).
  - Fill `evidence_url` and `verified_utc` for each updated rollup row.
  - Use `start_date_utc` / `end_date_utc` when known; otherwise leave windows open and note ambiguity.
- `registry/CHANGELOG.md`
  - Record what was added/changed, why, and expected impact on attribution coverage.

## Success Criteria

- [ ] Registry contains a credible, evidence-linked batcher/poster address set for the initial target rollup set
- [ ] Registry changes are logged with expected attribution impact
- [ ] `make gate` passes

## Status
- State: done
- Last updated: 2026-02-06
## Notes / Decisions

- 2026-01-30: Task created (Planner) to unblock on-chain attribution for a first coverage slice.



- 2026-02-06: Planner reconciliation — outputs already exist in repo; moved state to ready_for_review to clear control-plane drift before unattended fullscale preflight.


- 2026-02-06: Judge approval — promoted to done after repo-level gate/test/preflight checks and output existence verification to unblock downstream dependencies.
