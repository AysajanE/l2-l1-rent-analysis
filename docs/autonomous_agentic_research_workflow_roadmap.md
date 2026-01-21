# Autonomous Agentic Research Workflow (Reusable Architecture + Roadmap)

This document defines a reusable, file-based workflow for running multiple AI coding/research agents in parallel on empirical research projects with minimal conflict and minimal human babysitting.

It is designed to work with **subscription CLIs/IDEs** (e.g., Claude Code, Codex CLI) and does **not** assume API-based agent frameworks.

---

## 1) Design goals

**Goal:** A “research team in a repo” where agents can work in parallel, produce auditable outputs, and keep going unattended—while avoiding contradictions and clobbering.

**Non-goals (at first):**
- Not building a complex “agents talk to each other” system.
- Not relying on shared chat as the coordination substrate.
- Not attempting fully automated merges without quality gates.

---

## 2) The core architecture (Planner → Workers → Judge)

### Roles

- **Planner (human or agent)**
  - Reads the research plan + current repo state.
  - Decomposes work into small tasks with clear I/O contracts.
  - Assigns tasks to workstreams and defines ownership boundaries.

- **Workers (multiple agents)**
  - Each worker executes *one task at a time* in an isolated workspace (branch/worktree).
  - Writes outputs to the agreed paths and updates only the task’s `Status` + `Notes / Decisions`.
  - Does not coordinate directly with other workers.

- **Judge (human or agent)**
  - Runs deterministic checks (tests/validation/quality gates).
  - Reviews task success criteria against the outputs.
  - Accepts/requests revisions and merges via PRs/commits.

### Why this works

Parallelism fails when workers share mutable state (same branch, same files, “shared kanban brain” everyone edits).

This architecture prevents clashes by making conflicts structurally unlikely:
- **Isolation** (branches/worktrees) prevents accidental interference.
- **Contracts** (schemas, protocol lock, task specs) prevent definition drift.
- **Gates** prevent low-quality merges from propagating downstream.

---

## 3) “Repo as shared memory”: the coordination primitives

Everything important must live on disk in version control:

1. **`AGENTS.md` (the team contract)**
   - Non-negotiables, safety, scope rules, and “how we work here”.
   - Optional: add nested `AGENTS.md` in subdirectories for local rules.

2. **Protocol lock**
   - Canonical definitions (metrics, units, regimes, inclusion criteria).
   - The protocol is the highest-authority reference for downstream tasks.

3. **Workstreams + ownership boundaries**
   - Workstream definitions (“who owns what”).
   - Explicit “Owns paths” / “Does NOT own” rules.

4. **Task files**
   - Single Markdown task file per unit of work.
   - **Planner** moves task files across lifecycle folders.
   - Workers update only `Status` + `Notes / Decisions` (and set `State:` accordingly).

5. **Handoff notes**
   - Short integration notes for cross-task dependencies (paths, commands, assumptions).

6. **Quality gates**
   - Deterministic checks that run fast (structure checks, schema checks, unit tests, basic data sanity).

---

## 4) Reusable repo skeleton (minimum viable)

This repo uses the following coordination skeleton (copy to new projects as-is and customize the protocol + workstreams):

```text
.orchestrator/
  backlog/          # tasks not started
  active/           # tasks in progress
  blocked/          # blocked tasks (must include @human note)
  done/             # completed tasks
  handoff/          # cross-task notes
  templates/        # task + handoff templates
  workstreams.md    # ownership boundaries
docs/
  protocol.md       # protocol lock (definitions)
scripts/
  quality_gates.py  # fast deterministic checks
Makefile            # `make gate`
AGENTS.md           # global coordination contract
```

Recommended control-plane mode (bootstrapping): **PR-synchronized**
- Workers operate in isolated branches/worktrees.
- Status updates become visible when branches are pushed/PR’d (not real-time).

If you want deeper modularity for larger projects, expand to:
- `src/etl/`, `src/analysis/`, `src/validation/`
- `data/raw/` (append-only snapshots), `data/processed/`, `data/schemas/`
- `reports/` (figures, paper, deck)

---

## 5) Task design: how to make tasks parallelizable

### The “interface-first” rule

A task is parallelizable when it has:
- clear inputs (which files/data it reads),
- clear outputs (paths it produces),
- a stable interface (schema, function signature, registry format),
- and strict file ownership boundaries.

### Task sizing guidelines

Prefer tasks that take **30–180 minutes** for an agent to complete end-to-end.
If a task is larger, split it until it becomes interface-driven.

### Task template

Use `.orchestrator/templates/task_template.md`.

**Non-negotiable sections:**
- `## Outputs` (paths are your integration contract)
- `## Success Criteria` (what “done” means)
- `## Status` and `## Notes / Decisions` (the only sections workers edit)

---

## 6) Isolation and integration (how to prevent clashes)

### Isolation mechanisms

Choose one (in increasing robustness):

1. **Separate branches** per task (minimum).
2. **Git worktrees** per task (recommended for parallel local execution).
3. **Remote sandbox** (Codespaces/VM/devcontainer) per worker for unattended runs.
4. **Cloud agent tasks** (where available) that produce PRs for review.

### Integration mechanism (preferred)

- Every task integrates via PR (or at least a branch merge after judge checks).
- The Judge runs `make gate` (and any task-specific commands) before merging.

---

## 7) Continuous operation (agents work while you’re away)

To run unattended you need:
- an always-on machine (local desktop that won’t sleep, a VM, or Codespaces),
- a session manager (e.g., `tmux`) for long-running terminals,
- headless/non-interactive agent execution settings,
- strict safety boundaries (allowed tools, sandboxing, secrets discipline).

**Important:** “auto-approve tools” should only run in a sandboxed environment that contains *only* the repo and no sensitive files.

---

## 8) Roadmap (incremental implementation plan)

### Stage 0 — Reusable coordination layer (this repo now)

**Deliverables**
- `.orchestrator/` lifecycle folders + templates
- `AGENTS.md` rules
- `docs/protocol.md` protocol lock
- `make gate` runs fast and deterministically

**Success**
- A new agent can start a task without extra human context.

### Stage 1 — Parallel manual swarm (2–6 workers)

**Deliverables**
- Workstreams filled in `.orchestrator/workstreams.md`
- Worktrees/branches per task
- Judge process (human or agent) running gates and merging

**Success**
- Multiple tasks progress in parallel without file conflicts or definition drift.

### Stage 2 — Semi-automation (“job controller” scripts)

**Deliverables**
- Script(s) that:
  - pick ready tasks from `.orchestrator/backlog/`,
  - create worktrees/branches,
  - launch headless workers,
  - collect outputs + update task status.

**Success**
- Overnight progress without manual task launching.

### Stage 3 — Continuous supervisor loop

**Deliverables**
- Scheduled “tick” (cron-like) to:
  - assign tasks,
  - re-run gates,
  - reopen tasks as blocked with actionable notes,
  - produce a daily summary.

**Success**
- System runs continuously and only pings you for true decision points.

### Stage 4 — Reliability + evaluation

**Deliverables**
- Formal gate suite (data checks, schema drift checks, regression tests).
- “Fresh start” policy for long-running agents (restart from disk state periodically).
- Metrics: throughput, defect rate, rework rate, time-to-merge.

**Success**
- Sustained multi-week runs with low drift and minimal rework.

---

## 9) New-project bootstrap checklist (copy/paste)

1. Copy the skeleton:
   - `AGENTS.md`, `.orchestrator/`, `docs/protocol.md`, `scripts/quality_gates.py`, `Makefile`
2. Customize:
   - Protocol lock (definitions, regimes, inclusion criteria, tolerances)
   - Workstreams (`.orchestrator/workstreams.md`)
3. Create Phase 0 tasks:
   - Protocol lock
   - Data dictionary / schemas
   - Quality gates expansion
4. Run:
   - `make gate`
5. Start small:
   - 1 planner + 2 workers + 1 judge
6. Only then scale:
   - add more workers and increase parallel tasks
