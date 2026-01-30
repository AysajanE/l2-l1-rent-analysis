---
task_id: T094
title: "Analysis: EIP-7918 reserve/floor counterfactual module + figure"
workstream: W6
role: Worker
priority: medium
dependencies:
  - "T090"
  - "T093"
allowed_paths:
  - "src/analysis/counterfactual_eip7918.py"
  - "reports/figures/eip7918_counterfactual.svg"
  - "reports/tables/eip7918_counterfactual_summary.csv"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/etl/"
  - "data/raw/"
outputs:
  - "src/analysis/counterfactual_eip7918.py"
  - "reports/figures/eip7918_counterfactual.svg"
  - "reports/tables/eip7918_counterfactual_summary.csv"
gates:
  - "make gate"
stop_conditions:
  - "Need to introduce a new modeling assumption not covered by protocol"
---

# Task T094 — Analysis: EIP-7918 reserve/floor counterfactual module + figure

## Context

The research plan includes a policy counterfactual: how would a blob-fee floor/reserve mechanism (e.g., EIP-7918) have changed historical take rate?

This task implements a deterministic counterfactual module using the enriched v2 panel (which includes blob regime variables and any required macro inputs).

## Inputs

- `data/processed/panels/daily_rollup_panel_v2.parquet` (not committed; built by T090)
- `docs/end_to_end_research_plan.md` (read-only): counterfactual intent and presentation requirements
- `docs/protocol.md` (read-only): regime definitions and tolerances

## Outputs

- `src/analysis/counterfactual_eip7918.py`
  - Deterministic; no network calls.
  - Must state assumptions explicitly in the script docstring and output table metadata.
- `reports/figures/eip7918_counterfactual.svg`
- `reports/tables/eip7918_counterfactual_summary.csv`

## Success Criteria

- [ ] Assumptions are explicit and do not contradict protocol; if new assumptions are required, block with `@human`
- [ ] Outputs are reproducible from local processed inputs only
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-01-30

## Notes / Decisions

- 2026-01-30: Task created (Planner) to implement the policy counterfactual module in a reproducible way.

