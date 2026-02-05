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

- State: backlog
- Last updated: 2026-02-05

## Notes / Decisions

- 2026-02-05: Task created (Planner) to close the “blob fee at-minimum fraction + linkage to STR” completeness gap with deterministic sample artifacts.

