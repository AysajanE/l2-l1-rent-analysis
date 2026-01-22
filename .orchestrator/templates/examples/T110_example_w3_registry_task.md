---
task_id: T110
title: "Example W3 registry task (add/update attribution entries with evidence)"
workstream: W3
role: Worker
priority: medium
dependencies: []
allowed_paths:
  - "registry/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "src/etl/"
outputs:
  - "registry/rollup_registry_vX.csv"
  - "registry/CHANGELOG.md"
gates:
  - "make gate"
stop_conditions:
  - "Ambiguous attribution evidence"
---

# Task T110 — Example W3 registry task (add/update attribution entries with evidence)

## Context

Add or correct attribution entries (addresses/labels/rollups) in a versioned registry, with evidence links and a changelog entry describing expected impact.

## Assignment

- Workstream: W3 Registry
- Owner (agent/human):
- Suggested branch/worktree name: `T110_example_w3_registry`
- Allowed paths (edit/write): `registry/`
- Disallowed paths: `docs/protocol.md`, `contracts/`, `src/etl/`
- Stop conditions (escalate + block with `@human`):
  - Evidence is ambiguous or conflicting

## Inputs

- Evidence links (official docs/explorers):
- Prior handoffs:

## Outputs

- Versioned registry update (never delete entries; deprecate via fields if needed)
- `registry/CHANGELOG.md` entry (what changed, why, expected impact)

## Success Criteria

- [ ] Each new/updated entry includes evidence + date verified + notes on ambiguity
- [ ] Registry versioning is preserved (bump file version if interface changes)
- [ ] `make gate` passes

## Validation / Commands

- `make gate`

## Status

- State: backlog | active | blocked | ready_for_review | done
- Last updated: YYYY-MM-DD

## Notes / Decisions

- YYYY-MM-DD: Example notes go here.
