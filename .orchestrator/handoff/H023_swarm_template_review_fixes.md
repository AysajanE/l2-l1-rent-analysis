# Handoff H023 — Swarm template review fixes (Option A + integrity gates)

## Summary (1–3 sentences)

Implemented the review’s recommended hardening changes: governance Option A (automation updates `State:` only; Planner sweeps moves), simple concurrency controls, explicit STR/decomposition contracts, and stronger deterministic quality gates.

## What changed / what exists now

- Files/paths:
  - `scripts/swarm.py` (no lifecycle `git mv`; workstream concurrency + unattended safety interlock + timeouts)
  - `scripts/sweep_tasks.py` (Planner tool to move tasks based on `State:`)
  - `scripts/quality_gates.py` (dependency validity gate; contract/registry change discipline gates; sample integrity gate)
  - `scripts/make_raw_manifest.py` (requires `--as-of` or infers from snapshot dir; deterministic naming)
  - `contracts/schemas/panel_schema_str_v1.yaml` (STR panel schema)
  - `contracts/schemas/panel_schema_decomp_v1.yaml` (L1 rent decomposition stub)
  - `registry/rollup_registry_v1.csv` (registry header stub)
  - `data/processed_manifest/README.md` (processed manifest convention)
- Outputs produced:
  - Updated protocol edge-case rules + tolerances in `docs/protocol.md`
  - Narrowed `allowed_paths` in backlog tasks to reduce collisions

## How to reproduce / verify

- Commands:
  - `make gate`
  - `make test`
  - `python scripts/sweep_tasks.py --dry-run`
  - Unattended automation (external sandbox only): `SWARM_UNATTENDED_I_UNDERSTAND=1 python scripts/swarm.py tmux-start ... --unattended`
- Expected results:
  - Gates/tests pass; sweep dry-run prints planned moves (if any).

## Assumptions / risks

- The contract/registry change discipline gates compare against `origin/main` (or `main`); if neither ref exists locally, they skip. You can force a base via `GATE_BASE_REF`.
- `sample_panel_integrity` gate is skipped until a golden sample CSV is committed at `data/samples/growthepie/vendor_daily_rollup_panel_sample.csv`.

## Open questions / next steps

- Implement the vertical slice tasks (`T030`–`T060`) to populate the sample CSV, metrics, validation, and figure outputs.
- Fill `registry/rollup_registry_v1.csv` with evidence-backed entries and keep `registry/CHANGELOG.md` updated.
- Decide whether to keep `contracts/schemas/panel_schema.yaml` as an entrypoint-only file long-term or deprecate it once all references move to versioned schemas.
