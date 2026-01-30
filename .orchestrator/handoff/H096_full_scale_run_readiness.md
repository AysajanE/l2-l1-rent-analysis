# Handoff H096 — Full-scale swarm run readiness (docs + workstreams + backlog)

## Summary (1–3 sentences)

Aligned the end-to-end planning docs with the repo’s contract/registry/manifest conventions, refined workstreams for safe parallelism, blocked the “remove planning docs” task, and added a full-scale backlog (T080–T096) spanning contracts → ETL → panel builds → validation → analysis → writing.

## What changed / what exists now

- Workstreams + templates:
  - `.orchestrator/workstreams.md` refined ownership (added W8 Ops/Automation and W9 Data Products; clarified `parallel_ok`; added `data/processed_manifest/<source>_` ownership prefixes for W1/W2).
  - `.orchestrator/templates/task_template*.md` include `parallel_ok: false` by default.
- Docs:
  - `docs/end_to_end_data_collection_plan.md` updated to use repo paths (`data/raw_manifest/`, `data/processed_manifest/`, `reports/validation/`, `registry/`) and to reflect the contracted `daily_rollup_panel` minimum + v2 enrichment concept.
  - `docs/end_to_end_research_plan.md` now includes a short “Repo execution” section mapping protocol/contracts/registry/.orchestrator/reports/runbooks.
  - `docs/runbook_swarm.md` and `docs/runbook_swarm_automation.md` include Landlock fallbacks (`--codex-sandbox danger-full-access`) and tmux “press-go” examples.
- Control-plane conflict resolved:
  - `T070_remove_internal_docs_from_repo_head` moved to `.orchestrator/blocked/` and marked `State: blocked` (direction change: keep the end-to-end plan docs in repo HEAD for full-scale execution).
- New backlog tasks (full-scale DAG):
  - `.orchestrator/backlog/T080_...` through `.orchestrator/backlog/T096_...` (contracts, registry, off-chain ETL, on-chain ETL, panel v1/v2 builds, cross-source validation, STR metrics on v1 panel, analysis figures + counterfactual, writing drafts, processed-manifest helper script).

## How to reproduce / verify

- Commands run:
  - `make gate` (PASS)
  - `make test` (PASS; 1 test)
- Suggested next command before running the swarm:
  - `python scripts/swarm.py tick --planner heuristic --runner local --max-workers 5 --dry-run`

## Assumptions / risks

- **Stale claimed tasks**: swarm considers tasks “claimed” if remote branches/PRs exist with `T###_...` names. After heavy pilot testing, you may need to delete/close stale `T###_*` branches/PRs to allow a fresh run (see `docs/runbook_swarm_automation.md` → troubleshooting “claimed” tasks).
- Registry + on-chain attribution require evidence-backed address mappings; tasks T081/T082 can block with `@human` if evidence is ambiguous.
- Large on-chain extraction (T087) likely requires RPC credentials; task will block if unavailable.

## Next steps (recommended)

1. Commit + push these planning/control-plane updates on a clean branch and merge.
2. Ensure the task backlog is unclaimed (close/delete any stale `T###_*` PRs/branches you do not intend to merge).
3. Start a full run via tmux:
   - `SWARM_UNATTENDED_I_UNDERSTAND=1 python scripts/swarm.py tmux-start --tmux-session swarm --planner heuristic --max-workers <N> --create-pr --final-state ready_for_review --codex-sandbox danger-full-access --attach`
4. As the Planner: run periodic `make sweep` (manual or automated) to keep lifecycle folders aligned with `State:`.

