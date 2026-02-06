---
task_id: T096
title: "Ops: add helper script to generate processed manifests"
workstream: W8
role: Worker
priority: high
dependencies: []
parallel_ok: true
allowed_paths:
  - "scripts/make_processed_manifest.py"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "data/raw/"
outputs:
  - "scripts/make_processed_manifest.py"
gates:
  - "make gate"
stop_conditions:
  - "Gate requires non-deterministic behavior"
---

# Task T096 — Ops: add helper script to generate processed manifests

## Context

The repo standardizes raw snapshot manifests via `scripts/make_raw_manifest.py`, but processed artifacts also need tracked provenance (`data/processed_manifest/`). Right now the convention exists, but there is no standardized helper to create manifests consistently.

This task adds a deterministic helper script that:
- hashes one or more output files under `data/processed/`,
- records inputs (raw manifests and/or other processed manifests),
- captures the generating command and git SHA,
- writes a new append-only manifest file under `data/processed_manifest/`.

## Inputs

- `data/processed_manifest/README.md` (read-only): naming convention and required fields
- Existing raw-manifest helper: `scripts/make_raw_manifest.py` (read-only; mirror its UX where sensible)

## Outputs

- `scripts/make_processed_manifest.py`
  - Must be deterministic and offline.
  - Should support a CLI interface similar to `make_raw_manifest.py`.
  - Must not overwrite existing manifest files.

## Success Criteria

- [ ] Script generates a manifest that matches the documented convention (keys + structure)
- [ ] Script is deterministic and does not call the network
- [ ] `make gate` passes

## Status
- State: done
- Last updated: 2026-02-06
## Notes / Decisions

- 2026-01-30: Task created (Planner) to standardize processed provenance before scaling ETL tasks.



- 2026-02-06: Planner reconciliation — outputs already exist in repo; moved state to ready_for_review to clear control-plane drift before unattended fullscale preflight.


- 2026-02-06: Judge approval — promoted to done after repo-level gate/test/preflight checks and output existence verification to unblock downstream dependencies.
