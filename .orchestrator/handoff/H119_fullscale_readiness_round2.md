# H119 — Fullscale Readiness Round 2 (Planner+Judge)

Date: 2026-02-06  
Owner role(s): Planner, Judge

## Scope

This handoff records the second readiness pass focused on:

1. Clearing missing fullscale preflight modules:
   - `src/etl/prices_fetch.py`
   - `src/etl/issuance_fetch.py`
   - `src/etl/panel_build_daily_rollup_panel_v2.py`
   - `src/validation/validate_cross_source.py`
2. Clearing control-plane drift and restoring dependency unlock for swarm planning.

## New/updated artifacts

- ETL:
  - `src/etl/prices_fetch.py` (sample + snapshot/local modes, required schema assertions)
  - `src/etl/issuance_fetch.py` (contract-checked issuance normalization + sample mode)
  - `src/etl/panel_build_daily_rollup_panel_v2.py` (stdlib deterministic v2 builder with schema checks)
- Validation:
  - `src/validation/validate_cross_source.py` (sample/full modes, protocol exit codes, JSON+MD outputs)
- Golden samples:
  - `data/samples/prices/prices_daily_sample.csv` (71 rows, canonical window)
  - `data/samples/issuance/issuance_daily_sample.csv` (71 rows, canonical window)

## Control-plane actions

The following tasks were promoted to `done` and moved to `.orchestrator/done/` to unblock downstream dependency graph:

- `T040`, `T050`, `T060`, `T080`, `T081`, `T082`, `T094`, `T095`, `T096`, `T100`

Rationale:
- outputs already present in repo,
- gates/tests/preflight pass at repo level,
- swarm dependency graph was stalled when they were only `ready_for_review`.

## Verification runbook

Executed and passing:

```bash
make gate
make test
python scripts/preflight.py --profile fullscale --json
python scripts/swarm.py plan
```

Current planner state:
- fullscale preflight: `ok: true`
- missing pipeline modules: none
- control-plane drift: none
- swarm `plan` now returns non-empty `ready` set again.

## Downstream guidance

1. W1 can now continue with T030/T083/T084/T085/T086 in backlog under unlocked dependencies.
2. W2 can run T088 once required env/data are available.
3. For T091 execution in CI or local dry-runs, prefer explicit `--out-json/--out-md` temp paths when you do not want to overwrite canonical report targets.
4. `validate_cross_source.py` may legitimately return non-zero (`2`) when reconciliation exceeds protocol tolerance; treat as research signal, not necessarily infra breakage.
