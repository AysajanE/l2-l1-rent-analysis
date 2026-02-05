---
task_id: T103
title: "Analysis: burn vs issuance time series (sample mode)"
workstream: W6
role: Worker
priority: medium
dependencies:
  - "T090"
parallel_ok: true
allowed_paths:
  - "src/analysis/plot_burn_vs_issuance.py"
  - "reports/figures/burn_vs_issuance_sample.svg"
  - "reports/tables/burn_vs_issuance_sample.csv"
  - "reports/tables/burn_vs_issuance_sample_run.json"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/etl/"
  - "data/raw/"
outputs:
  - "src/analysis/plot_burn_vs_issuance.py"
  - "reports/figures/burn_vs_issuance_sample.svg"
  - "reports/tables/burn_vs_issuance_sample.csv"
  - "reports/tables/burn_vs_issuance_sample_run.json"
gates:
  - "make gate"
stop_conditions:
  - "Missing sample inputs"
  - "Issuance definition ambiguity requires @human"
---

# Task T103 — Analysis: burn vs issuance time series (sample mode)

## Context

For “burn vs issuance” context (and related framing around rent capture and net issuance), we need a deterministic, offline time series that combines:
- issuance (gross, consensus-layer) from the W0-locked definition, and
- on-chain burn components (execution base fee burn + blob fee burn) where available.

This task produces sample-mode outputs from the enriched v2 panel sample so the pipeline stays reproducible in CI and swarm runs.

## Inputs

- `data/samples/panels/daily_rollup_panel_v2_sample.csv` (committed; produced by T090)
- `docs/protocol.md` (read-only): issuance definition + units; Dencun boundary for blob burn interpretation
- `contracts/schemas/panel_schema_str_v2.yaml` (read-only): expected issuance + burn component field names

## Outputs

- `src/analysis/plot_burn_vs_issuance.py`
  - Deterministic; no network calls.
  - Must support `--sample` mode (default) reading from committed `data/samples/`.
  - May optionally support `--panel <path>` for full runs.
- `reports/figures/burn_vs_issuance_sample.svg`
  - Stable sample-mode figure name.
  - Should show daily issuance alongside burn components (and optionally derived net issuance) with regime annotation at Dencun.
- `reports/tables/burn_vs_issuance_sample.csv`
  - Daily series containing issuance + burn component aggregates used in the figure.
- `reports/tables/burn_vs_issuance_sample_run.json`
  - Traceability: timestamp, command, git SHA (if available), and input/output hashes (repo-relative paths only).

## Success Criteria

- [ ] Script runs in `--sample` mode and writes the outputs above
- [ ] Issuance series uses the W0-locked definition (gross issuance; not net of burn)
- [ ] Output schema is asserted (required columns exist; fail fast on schema mismatch)
- [ ] Outputs are deterministic for the committed sample inputs
- [ ] `make gate` passes

## Status

- State: backlog
- Last updated: 2026-02-05

## Notes / Decisions

- 2026-02-05: Task created (Planner) to close the “burn vs issuance time series” completeness gap with deterministic sample artifacts.

