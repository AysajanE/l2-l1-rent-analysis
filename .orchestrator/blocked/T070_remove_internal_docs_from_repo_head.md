---
task_id: T070
title: "Remove internal planning docs from repo HEAD"
workstream: W7
role: Worker
priority: medium
dependencies: []
allowed_paths:
  - "docs/discussion_on_building_autonomous_AI_agents_research_workflow.md"
  - "docs/end_to_end_research_plan.md"
  - "docs/end_to_end_data_collection_plan.md"
  - ".gitignore"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - ".orchestrator/templates/"
  - ".orchestrator/workstreams.md"
  - "data/raw/"
outputs:
  - ".gitignore"
gates:
  - "make gate"
stop_conditions:
  - "Need to remove additional files not listed in allowed_paths"
  - "Quality gate failure requires protocol/contract changes"
---

# Task T070 — Remove internal planning docs from repo HEAD

## Context

Some `docs/` files contain internal planning/discussion content that should not be present in the public GitHub repository HEAD. We will remove them from the tracked repo state (no history rewrite) and add ignore rules to reduce accidental re-add.

## Assignment

- Workstream: W7
- Owner (agent/human): Codex CLI
- Suggested branch/worktree name: `T070_remove_internal_docs_from_repo_head`
- Allowed paths (edit/write): see frontmatter
- Disallowed paths: see frontmatter
- Stop conditions (escalate + block with `@human`): see frontmatter

## Inputs

- Repo paths:
  - `docs/discussion_on_building_autonomous_AI_agents_research_workflow.md`
  - `docs/end_to_end_research_plan.md`
  - `docs/end_to_end_data_collection_plan.md`

## Outputs

- Git: remove the files from tracked HEAD
- `.gitignore`: add explicit ignore rules for the removed docs

## Success Criteria

- [ ] The listed docs are not present in the tracked repo HEAD
- [ ] `.gitignore` prevents accidental re-add of the removed docs
- [ ] `make gate` passes
- [ ] PR opened against `main`

## Validation / Commands

- `make gate`

## Worker edit rules

- **Workers edit only** `## Status` and `## Notes / Decisions`.
- **Workers do not move this file** between lifecycle folders; set `State:` and the Planner will sweep.

## Status

- State: blocked
- Last updated: 2026-01-30

## Notes / Decisions

- 2026-01-30: Task created to remove internal docs from public HEAD (no history rewrite).
- 2026-01-30: Opened PR #25; removed 3 docs from tracked HEAD; updated `.gitignore`; `make gate` passed.
- 2026-01-30: BLOCKED @human — Direction change: `docs/end_to_end_research_plan.md` and `docs/end_to_end_data_collection_plan.md` are now treated as foundational, actively maintained planning docs for the full-scale swarm run. Do not merge PR #25 as-is; revisit public-release posture (e.g., move/redact truly internal docs only).
