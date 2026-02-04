# Handoff H111 — Rollup registry integrity gate (non-empty + parseable)

## Summary (1–3 sentences)

Added a new quality gate that fails fast if `registry/rollup_registry_v1.csv` is empty or contains non-parseable / non-conforming `batcher_addresses_json`. This prevents downstream ETL/tasks from implicitly assuming a populated registry and drifting on `rollup_id` semantics.

## What changed / what exists now

- Files/paths:
  - `scripts/quality_gates.py`: adds `rollup_registry_integrity` gate and requires `registry/README.md` + `registry/schemas/batcher_addresses_json_v1.schema.json` to exist.
  - `src/etl/panel_build_daily_rollup_panel_v1.py`: errors with a clear message if the registry CSV has zero rows.
- Outputs produced:
  - No new data artifacts; this is guardrail + validation only.

## How to reproduce / verify

- Commands:
  - `make gate`
  - `make test`
- Expected results:
  - `make gate` prints `[rollup_registry_integrity] ok=True ...` when the registry is seeded and JSON is valid.
  - If the registry is header-only (or `batcher_addresses_json` is invalid JSON), `make gate` exits non-zero with actionable `failures[]`.

## Assumptions / risks

- The integrity gate currently enforces that **in-scope** rows have non-empty `origin_key`, `l2beat_slug`, `evidence_url`, `verified_utc`, and a non-empty `batcher_addresses_json` object conforming to schema v1.
  - If you want to add a long-tail rollup without deterministic joins yet, set `in_scope=false` until mappings are filled.
- Schema changes (e.g., `schema_version: 2`) will require updating the gate validator accordingly.

## Open questions / next steps

- Consider wiring semantic dependency fixes in the control plane (Planner): ensure any ETL task that needs deterministic joins references the seeded registry and/or depends on the registry seeding task(s).

