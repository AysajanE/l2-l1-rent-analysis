---
task_id: T102
title: "Analysis: blob fee at-minimum fraction + STR linkage (sample mode)"
workstream: W6
role: Worker
priority: medium
dependencies:
  - "T090"
parallel_ok: true
allowed_paths:
  - "src/analysis/blob_floor_binding_str_link.py"
  - "reports/figures/blob_floor_binding_str_link_sample.svg"
  - "reports/tables/blob_floor_binding_str_link_sample.csv"
  - "reports/tables/blob_floor_binding_str_link_sample_run.json"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/etl/"
  - "data/raw/"
outputs:
  - "src/analysis/blob_floor_binding_str_link.py"
  - "reports/figures/blob_floor_binding_str_link_sample.svg"
  - "reports/tables/blob_floor_binding_str_link_sample.csv"
  - "reports/tables/blob_floor_binding_str_link_sample_run.json"
gates:
  - "make gate"
stop_conditions:
  - "Missing sample inputs"
  - "Regime definition ambiguity requires @human"
---

# Task T102 — Analysis: blob fee at-minimum fraction + STR linkage (sample mode)

## Context

The research plan calls for blob-regime analysis, including “at-minimum” / floor-binding periods, and their relationship to STR dynamics post‑Dencun.

This task produces deterministic sample-mode outputs that:
- compute an “at-minimum” / floor-binding indicator from integer-safe blob base fee inputs (wei), and
- relate it to daily ecosystem STR (e.g., correlation, conditional means, simple comparison plots).

## Inputs

- `data/samples/panels/daily_rollup_panel_v2_sample.csv` (committed; produced by T090)
- `contracts/schemas/panel_schema_str_v2.yaml` (read-only): required field names/units
- `docs/protocol.md` (read-only):
  - Dencun boundary (`2024-03-13` UTC),
  - blob fee regime definition (integer-safe `l1_blob_base_fee_wei` rules),
  - validation tolerances (when referencing regime windows).

## Outputs

- `src/analysis/blob_floor_binding_str_link.py`
  - Deterministic; no network calls.
  - Must support `--sample` mode (default) reading from committed `data/samples/`.
  - May optionally support `--panel <path>` for full runs.
- `reports/figures/blob_floor_binding_str_link_sample.svg`
  - Stable sample-mode figure name.
  - Should include at-minimum/floor-binding annotations and STR series/summary comparisons.
- `reports/tables/blob_floor_binding_str_link_sample.csv`
  - Daily series containing: `date_utc`, ecosystem STR, blob base fee (wei), and the derived indicator(s).
- `reports/tables/blob_floor_binding_str_link_sample_run.json`
  - Traceability: timestamp, command, git SHA (if available), and input/output hashes (repo-relative paths only).

## Success Criteria

- [ ] Script runs in `--sample` mode and writes the outputs above
- [ ] Regime computation uses integer-safe wei inputs (no floating gwei for regime logic)
- [ ] Output schema is asserted (required columns exist; fail fast on schema mismatch)
- [ ] Outputs are deterministic for the committed sample inputs
- [ ] `make gate` passes

## Status
- State: done
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-02-05: Task created (Planner) to close the “blob fee at-minimum fraction + linkage to STR” completeness gap with deterministic sample artifacts.



- 2026-02-10: Claimed by swarm runner; starting worker (branch: T102_analysis_blob_floor_binding_and_str_link_sample).


- 2026-02-10: Implemented deterministic sample-mode blob at-minimum / floor-binding regime computation and linked it to ecosystem STR. Outputs:
  - `src/analysis/blob_floor_binding_str_link.py`
  - `reports/tables/blob_floor_binding_str_link_sample.csv`
  - `reports/figures/blob_floor_binding_str_link_sample.svg`
  - `reports/tables/blob_floor_binding_str_link_sample_run.json`
  Repro: `python src/analysis/blob_floor_binding_str_link.py --sample`
  Notes: Protocol floor-binding regime is defined as contiguous runs of >=7 post-Dencun days where `l1_blob_base_fee_wei <= (min_post * 105)//100` (integer-safe). On the committed v2 sample (2024-02-20..2024-04-30), at-minimum days are 24/49 post-Dencun (~49.0%), but no >=7-day contiguous floor-binding regime occurs (indicator remains 0). Gates: `make gate` OK; `make test` OK.


- 2026-02-10: Judge: gates ok; ownership ok. Review log: /tmp/swarm-worktrees/wt-T102/data/tmp/swarm_logs/T102_20260210T115127Z_judge_review.txt
