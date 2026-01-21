# Agent Operating Manual (read this first)

You are working in a **multi-agent research repo**.

## Non-negotiable rules
1. **Do not coordinate via chat with other agents.** Coordination happens through files in `.orchestrator/`.
2. **Do not modify files outside your task scope** unless the task explicitly authorizes it.
3. **Prefer small, verifiable changes.** Run the relevant checks before declaring done.
4. **Never edit raw data snapshots in-place.** Treat `data/raw/` as append-only.

## Task lifecycle
- Each task is a Markdown file. Workers update only:
  - the `Status` section
  - the `Notes / Decisions` section
- If blocked, write a short blocker note and move the task file to `.orchestrator/blocked/`.

## Definition of Done
A task is done when:
- Success criteria are met
- Relevant tests/quality gates pass
- Outputs are saved to the agreed paths

## Communication
- Questions to human: create a blocker note in the task file tagged `@human`.
- Cross-task handoffs: write a short note in `.orchestrator/handoff/`.
