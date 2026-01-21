# Research Swarm Template (membership-friendly)

This template is a lightweight, *file-based* orchestration system for running multiple coding/research agents in parallel (e.g., Claude Code + OpenAI Codex), while keeping coordination sane.

## Core idea
- **Planner** writes/updates task specs in `.orchestrator/`.
- **Workers** execute *one task each* in isolated git worktrees/branches.
- **Judge** runs quality gates + reviews diffs, then either requests fixes or approves merge.

## Why this structure
- A shared “Kanban file” where agents self-coordinate is fragile at scale.
- Git branches/worktrees + task specs + automated gates are the simplest robust coordination mechanism.

## Directory layout
- `.orchestrator/` — task queue + state (single source of truth)
- `docs/` — protocol, definitions, data dictionary
- `src/` — ETL, validation, analysis
- `data/` — raw/processed/schemas (keep large artifacts out of git)

## Minimal operating procedure
1. Fill `docs/protocol.md` and `data/schemas/` (Phase 0).
2. Planner creates tasks in `.orchestrator/backlog/` with success criteria.
3. Start multiple Workers (tmux panes) and assign each a task file.
4. Worker opens PR (or commits to its branch).
5. Judge runs `make gate` and reviews diff vs success criteria.
6. Merge + repeat.

## Safety defaults
- Don’t run “auto-approve everything” on your laptop.
- Prefer a sandboxed environment (Codespaces/VM/devcontainer).
- Restrict file access and dangerous shell commands where possible.
