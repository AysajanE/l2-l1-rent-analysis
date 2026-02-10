# Handoff H126 — Swarm Run Status + QC + Incident Log (2026-02-10)

## Summary (1-3 sentences)

As of `2026-02-10T13:45Z`, the swarm supervisor is running but idle because there are **no ready tasks** (`python scripts/swarm.py plan` shows `ready: []`). `main` is green (`make gate`, `make test` pass) and the most recent merge to `main` was at `2026-02-10T12:00:21Z` (PR `#51`).

## Current Status Snapshot

- Timestamp (UTC): `2026-02-10T13:45Z`
- `main` HEAD: `78146be` (merged via PR `#51` at `2026-02-10T12:00:21Z`)
- Swarm plan: `ready: []`, `done` includes `T101/T102/T103`.
- `gh pr list --state open`: none.
- Blocked tasks remain:
  - `.orchestrator/blocked/T070_remove_internal_docs_from_repo_head.md` (explicit @human direction change)
  - `.orchestrator/blocked/T087_onchain_etl_l1_raw_extract_headers_txs_receipts.md` (deprecated/superseded by T087A/B/C)

Note: tasks can remain physically under `.orchestrator/backlog/` even when `State: done` (Planner sweep moves files). This can look like “backlog exists” even when scheduler has no runnable tasks.

## Work Completed (High-Level)

Recent merged PRs (UTC):
- `#51` `2026-02-10T12:00:21Z` — `T103` burn vs issuance sample analysis outputs.
- `#50` `2026-02-10T11:56:58Z` — supervisor hardening: avoid crashing on worktree-prep races.
- `#49` `2026-02-10T11:55:41Z` — `T101` rent decomposition sample analysis outputs.
- `#48` `2026-02-10T11:51:55Z` — `T102` blob floor binding + STR linkage sample analysis outputs.
- `#47` `2026-02-10T11:37:53Z` — control-plane fix: mark `T090` done so `T101/T102/T103` can run.

Key committed artifacts now present:
- Analysis scripts:
  - `src/analysis/plot_rent_decomposition.py`
  - `src/analysis/blob_floor_binding_str_link.py`
  - `src/analysis/plot_burn_vs_issuance.py`
- Sample report outputs:
  - `reports/figures/rent_decomposition_sample.svg`
  - `reports/tables/rent_decomposition_sample.csv`
  - `reports/tables/rent_decomposition_sample_run.json`
  - `reports/figures/blob_floor_binding_str_link_sample.svg`
  - `reports/tables/blob_floor_binding_str_link_sample.csv`
  - `reports/tables/blob_floor_binding_str_link_sample_run.json`
  - `reports/figures/burn_vs_issuance_sample.svg`
  - `reports/tables/burn_vs_issuance_sample.csv`
  - `reports/tables/burn_vs_issuance_sample_run.json`

## Quality Checks Run

- `make gate` (pass)
- `make test` (pass; `Ran 46 tests`)

Quick content sanity:
- Outputs are present under `reports/figures/` and `reports/tables/` and sizes are reasonable (SVG/CSV kilobytes).
- No open PRs.

## Incidents / Unexpected Events Observed (and Fixes)

1) Scheduler idle due to stale control-plane task state
- Symptom: supervisor printed `No ready tasks in backlog.` even though downstream tasks should have been runnable.
- Root cause: `.orchestrator/backlog/T090_panel_build_daily_rollup_panel_v2_enriched.md` remained `State: blocked` after PR `#45` merged.
- Fix: PR `#47` marked `T090` `State: done`, enabling `T101/T102/T103` scheduling.

2) Supervisor pane exited due to git worktree/branch race
- Symptom: tmux `supervisor` pane died with error similar to `fatal: cannot lock ref ... reference already exists`.
- Root cause: `cmd_loop()` exits in unattended mode on any exception, and `ensure_worktree()` raises when a branch already exists (e.g. manual `tick` invoked while `loop` also ticks, or restart timing).
- Fix: PR `#50` updated `scripts/swarm.py` so `tick` logs and **skips** tasks when worktree preparation fails, instead of propagating and killing the loop.

3) Env var name mismatch and supervisor env propagation
- Symptom (earlier in run): some on-chain tasks expected `ETH_RPC_URL`, but `.env` contained `ETHEREUM_RPC_URL`.
- Fix applied operationally: supervisor command now exports `ETH_RPC_URL` from `.env` at runtime (value redacted; no secrets committed).
- Follow-up suggestion: standardize on a single env var name in task `required_env` and scripts, or support both consistently.

4) Auto-merge gating is not enforced by branch protection
- Observation: GitHub API reports `main` branch is not protected.
- Practical impact: GitHub can merge PRs without waiting for Actions checks.
- Mitigation: the swarm judge runs `make gate` before setting tasks `done`, but a branch protection rule requiring `gate`/`test` would add defense-in-depth.

## QC Notes / Potential Improvements

- Several `*_run.json` manifests include `created_at_utc`/`timestamp_utc` with wall-clock time and sometimes `git_sha`/`git_commit` is `null`.
  - This is OK for traceability as committed artifacts, but reruns are not byte-for-byte deterministic due to timestamps.
  - Suggestion: allow `--as-of` to fully drive the timestamp field, and ensure git SHA is always populated (runner can inject it if `git` is unavailable in sandbox).

- tmux session retains many historical windows (`T030`, `T083`, etc.). Not harmful, but can cause operator confusion. Suggest periodic cleanup or naming conventions.

## How to Reproduce / Verify

- Status:
  - `python scripts/swarm.py plan`
  - `tmux capture-pane -t swarm:1 -p | tail -n 80`
  - `gh pr list --state open`

- QC:
  - `make gate`
  - `make test`

## Open Questions / Next Steps

- If additional work is expected, new task files must be added under `.orchestrator/backlog/` (with correct dependencies) or the Planner must sweep/move lifecycle folders as needed.
- Consider enabling branch protection on `main` and requiring at least the CI gate checks.
