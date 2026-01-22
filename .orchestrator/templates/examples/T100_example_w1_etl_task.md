---
task_id: T100
title: "Example W1 ETL task (off-chain source → raw snapshot + manifest)"
workstream: W1
role: Worker
priority: medium
dependencies: []
allowed_paths:
  - "src/etl/"
  - "data/raw/"
  - "data/raw_manifest/"
  - "data/processed/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
outputs:
  - "src/etl/example_source_fetch.py"
  - "data/raw/example_source/YYYY-MM-DD/..."
  - "data/raw_manifest/example_source_YYYY-MM-DD.json"
gates:
  - "make gate"
stop_conditions:
  - "Need credentials"
  - "Source instability / breaking changes"
---

# Task T100 — Example W1 ETL task (off-chain source → raw snapshot + manifest)

## Context

Fetch a small off-chain dataset from a stable public source, snapshot it under `data/raw/`, and write a tracked manifest under `data/raw_manifest/` so downstream work is reproducible.

## Assignment

- Workstream: W1 Data: off-chain
- Owner (agent/human):
- Suggested branch/worktree name: `T100_example_w1_etl`
- Allowed paths (edit/write): `src/etl/`, `data/raw/`, `data/raw_manifest/`, `data/processed/`
- Disallowed paths: `docs/protocol.md`, `contracts/`, `registry/`
- Stop conditions (escalate + block with `@human`):
  - Need credentials or paid API keys
  - Source is unstable or undocumented

## Inputs

- Source docs/endpoint:
- Prior tasks / handoffs:

## Outputs

- Raw snapshots (append-only): `data/raw/example_source/<YYYY-MM-DD>/...`
- Provenance manifest (tracked): `data/raw_manifest/example_source_<YYYY-MM-DD>.json`
- Optional normalized extract: `data/processed/example_source/...`
- ETL code under `src/etl/`

## Success Criteria

- [ ] Snapshot is dated and immutable (no overwrites)
- [ ] Manifest exists and includes `files[{path,sha256,bytes}]`
- [ ] Repro command is documented (what to run, expected outputs)
- [ ] `make gate` passes

## Validation / Commands

- `make gate`
- Example manifest command:
  - `python scripts/make_raw_manifest.py example_source data/raw/example_source/<YYYY-MM-DD> "python src/etl/example_source_fetch.py --date <YYYY-MM-DD>"`

## Status

- State: backlog | active | blocked | ready_for_review | done
- Last updated: YYYY-MM-DD

## Notes / Decisions

- YYYY-MM-DD: Example notes go here.
