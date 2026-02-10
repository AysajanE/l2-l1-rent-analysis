---
task_id: T101
title: "Analysis: rent decomposition plots over time (sample mode)"
workstream: W6
role: Worker
priority: medium
dependencies:
  - "T090"
parallel_ok: true
allowed_paths:
  - "src/analysis/plot_rent_decomposition.py"
  - "reports/figures/rent_decomposition_sample.svg"
  - "reports/tables/rent_decomposition_sample.csv"
  - "reports/tables/rent_decomposition_sample_run.json"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/etl/"
  - "data/raw/"
outputs:
  - "src/analysis/plot_rent_decomposition.py"
  - "reports/figures/rent_decomposition_sample.svg"
  - "reports/tables/rent_decomposition_sample.csv"
  - "reports/tables/rent_decomposition_sample_run.json"
gates:
  - "make gate"
stop_conditions:
  - "Missing sample inputs"
  - "Need to introduce a new decomposition definition not covered by protocol/contracts"
---

# Task T101 — Analysis: rent decomposition plots over time (sample mode)

## Context

The research goals require explaining STR mechanisms via decomposition:
- burn vs tips, and
- blob vs execution (post‑Dencun).

This task adds a deterministic, offline analysis script that produces a sample-mode figure/table using the enriched v2 panel sample (so CI and swarm runs stay reproducible).

## Inputs

- `data/samples/panels/daily_rollup_panel_v2_sample.csv` (committed; produced by T090)
- `contracts/schemas/panel_schema_str_v2.yaml` (read-only): required field names/units
- `docs/protocol.md` (read-only): regime boundaries (Dencun date) and decomposition semantics

## Outputs

- `src/analysis/plot_rent_decomposition.py`
  - Deterministic; no network calls.
  - Must support `--sample` mode (default) reading from `data/samples/`.
  - May optionally support `--panel <path>` for full runs (no requirement to commit full outputs here).
- `reports/figures/rent_decomposition_sample.svg`
  - Stable figure name (sample mode).
  - Should show time series of component shares (e.g., blob burn share; tips share) and/or stacked components.
- `reports/tables/rent_decomposition_sample.csv`
  - Daily aggregate decomposition components/shares used in the figure.
- `reports/tables/rent_decomposition_sample_run.json`
  - Traceability: timestamp, command, git SHA (if available), and input/output hashes (repo-relative paths only).

## Success Criteria

- [ ] Script runs in `--sample` mode and writes the outputs above
- [ ] Output schema is asserted (required columns exist; fail fast on schema mismatch)
- [ ] Outputs are deterministic for the committed sample inputs
- [ ] `make gate` passes

## Status
- State: done
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-02-05: Task created (Planner) to close the “decomposition plots over time” completeness gap using deterministic sample-mode artifacts.



- 2026-02-10: Claimed by swarm runner; starting worker (branch: T101_analysis_rent_decomposition_plots_sample).

- 2026-02-10: Implemented deterministic sample-mode rent decomposition artifacts.
  - Added: `src/analysis/plot_rent_decomposition.py`
  - Generated (sample mode):
    - `reports/figures/rent_decomposition_sample.svg`
    - `reports/tables/rent_decomposition_sample.csv`
    - `reports/tables/rent_decomposition_sample_run.json`
  - Repro:
    - `python src/analysis/plot_rent_decomposition.py --sample`
  - Gates:
    - `make gate` => pass
    - `make test` => pass (`Ran 46 tests`)
  - Notes:
    - The committed v2 sample fixture has empty `rent_base_fee_burn_eth` / `rent_priority_fee_eth` (coverage recorded in the run manifest). Sample-mode therefore primarily illustrates blob-burn share vs non-blob share post-Dencun.
  - Handoff: `.orchestrator/handoff/H125_T101_rent_decomposition_plots_sample.md`


- 2026-02-10: Judge: gates ok; ownership ok. Review log: /tmp/swarm-worktrees/wt-T101/data/tmp/swarm_logs/T101_20260210T115513Z_judge_review.txt
