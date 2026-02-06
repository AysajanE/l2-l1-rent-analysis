---
task_id: T095
title: "Writing: draft paper + deck outline with figure/table references"
workstream: W7
role: Worker
priority: low
dependencies:
  - "T093"
  - "T094"
allowed_paths:
  - "reports/paper/str_take_rate_draft.md"
  - "reports/deck/str_take_rate_deck_outline.md"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/"
  - "data/raw/"
outputs:
  - "reports/paper/str_take_rate_draft.md"
  - "reports/deck/str_take_rate_deck_outline.md"
gates:
  - "make gate"
stop_conditions:
  - "Missing core figures/tables"
---

# Task T095 — Writing: draft paper + deck outline with figure/table references

## Context

Once the core figures and counterfactual outputs exist, we need a narrative skeleton that:
- states the question and hypotheses,
- describes the protocol lock and data provenance,
- presents the core STR results,
- presents the counterfactual,
- highlights limitations and next steps.

This task produces lightweight drafts that reference the generated artifacts (figures/tables) without manually editing those artifacts.

## Inputs

- `docs/end_to_end_research_plan.md` (read-only): narrative outline and hypotheses
- Generated artifacts:
  - `reports/figures/str_timeseries_full.svg`
  - `reports/tables/str_summary_full.csv`
  - `reports/figures/eip7918_counterfactual.svg`
  - `reports/tables/eip7918_counterfactual_summary.csv`

## Outputs

- `reports/paper/str_take_rate_draft.md`
  - A structured draft (sections + bullet points are fine at first).
  - Must cite which figures/tables support each claim.
- `reports/deck/str_take_rate_deck_outline.md`
  - Slide-by-slide outline referencing the same artifacts.

## Success Criteria

- [ ] Drafts reference concrete artifacts and avoid speculative claims beyond what the figures support
- [ ] Drafts include an explicit limitations section aligned with the research plan
- [ ] `make gate` passes

## Status
- State: ready_for_review
- Last updated: 2026-02-06
## Notes / Decisions

- 2026-01-30: Task created (Planner) to turn computed artifacts into a stakeholder-ready narrative.



- 2026-02-06: Planner reconciliation — outputs already exist in repo; moved state to ready_for_review to clear control-plane drift before unattended fullscale preflight.
