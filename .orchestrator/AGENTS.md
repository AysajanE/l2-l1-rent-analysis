# .orchestrator/AGENTS.md — Control Plane Rules

This directory is the repo’s coordination layer.

## MUST

- Treat orchestrator files as control-plane interfaces for the swarm. Avoid silent behavior changes.

- **Planner only**:
  - moves tasks across folders (`backlog/`, `active/`, `ready_for_review/`, `blocked/`, `done/`)
  - edits `workstreams.md`
  - edits anything in `templates/`
- **Worker may**:
  - edit ONLY their assigned task file
  - edit ONLY `## Status` and `## Notes / Decisions`
  - add a new handoff note in `handoff/` using the template
- **Judge may**:
  - change task `State:` to `ready_for_review` or `done` after gates pass
  - request revisions in `Notes / Decisions`

## Task claiming (if instructed by Planner)

Workers do NOT self-assign tasks unless the Planner explicitly says so.

## Status discipline

- Always update `Last updated` in UTC date (YYYY-MM-DD).
- `State` must be one of:
  `backlog | active | blocked | ready_for_review | done`
- If blocked: include `@human` and the smallest decision needed.

## SHOULD

- Prefer additive changes in orchestration semantics over removals/renames.
- If changing orchestration keys or semantics, update:
  - `docs/runbook_swarm*.md`
  - relevant templates in `.orchestrator/templates/`
  - parser/validator logic in `scripts/` and tests
- Keep machine-readable files valid (YAML/JSON/Markdown structure) after edits.

## DO NOT

- Do not rewrite task context/history. Append notes, do not overwrite history.
- Do not embed secrets in orchestration files.
- Do not change pipeline semantics quietly without documenting the change.
