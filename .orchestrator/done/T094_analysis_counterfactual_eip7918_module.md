---
task_id: T094
title: "Analysis: EIP-7918 reserve/floor counterfactual module + figure"
workstream: W6
role: Worker
priority: medium
dependencies:
  - "T090"
  - "T096"
  - "T098"
allowed_paths:
  - "src/analysis/counterfactual_eip7918.py"
  - "data/samples/panels/daily_rollup_panel_v2_sample.csv"
  - "data/samples/panels/README.md"
  - "reports/figures/eip7918_counterfactual_sample.svg"
  - "reports/tables/eip7918_counterfactual_summary_sample.csv"
  - "reports/tables/eip7918_counterfactual_summary_sample_run.json"
  - "reports/figures/eip7918_counterfactual_full.svg"
  - "reports/tables/eip7918_counterfactual_summary_full.csv"
  - "reports/tables/eip7918_counterfactual_summary_full_run.json"
  - "tests/test_counterfactual_eip7918_sample.py"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/etl/"
  - "data/raw/"
outputs:
  - "src/analysis/counterfactual_eip7918.py"
  - "data/samples/panels/daily_rollup_panel_v2_sample.csv"
  - "reports/figures/eip7918_counterfactual_sample.svg"
  - "reports/tables/eip7918_counterfactual_summary_sample.csv"
  - "reports/tables/eip7918_counterfactual_summary_sample_run.json"
  - "tests/test_counterfactual_eip7918_sample.py"
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

- Sample panel (committed):
  - `data/samples/panels/daily_rollup_panel_v2_sample.csv`
- Full panel (not committed; produced by T090):
  - `data/processed/panels/daily_rollup_panel_v2.csv`
  - `data/processed_manifest/daily_rollup_panel_v2_YYYY-MM-DD.json` (required for provenance capture)
- W0 locks (read-only; must not introduce new assumptions in W6):
  - `docs/protocol.md`: EIP-7918 parameterization + regime definitions
  - `contracts/assumptions.md`: A001 (applied-floor counterfactual assumption)
  - `contracts/decisions.md`: EIP-7918 decision entry + expected inputs/units

## Outputs

- `src/analysis/counterfactual_eip7918.py`
  - Deterministic; no network calls.
  - Must support both `--sample` and `--panel` modes.
  - Must state assumptions explicitly in the script docstring and output table metadata.
- Generated artifacts (stable names; sample outputs committed for CI):
  - `reports/tables/eip7918_counterfactual_summary_sample.csv`
    - First line must include a machine-readable metadata block: `# meta_json: {...}`
    - Must include assumption IDs + constants + input panel sha256 (and full-mode panel manifest sha256).
  - `reports/figures/eip7918_counterfactual_sample.svg`
  - `reports/tables/eip7918_counterfactual_summary_sample_run.json` (traceability: assumptions + inputs/outputs + hashes)
- Full-mode artifacts (not committed by default; stable `full` tag):
  - `reports/tables/eip7918_counterfactual_summary_full.csv`
  - `reports/figures/eip7918_counterfactual_full.svg`
  - `reports/tables/eip7918_counterfactual_summary_full_run.json`

## Success Criteria

- [ ] Assumptions are explicit and match the W0 locks (T098); if new assumptions are required, block with `@human`
- [ ] Script supports `--sample` mode and produces the committed sample artifacts under `reports/`
- [ ] Script supports full mode via `--panel <path> --panel-manifest <path> --tag full`
- [ ] Summary CSV includes machine-readable metadata capturing assumptions and input panel manifest hash (full mode)
- [ ] Sample outputs are deterministic (covered by unit test)
- [ ] `make gate` passes

## Status
- State: done
- Last updated: 2026-02-06
## Notes / Decisions

- 2026-01-30: Task created (Planner) to implement the policy counterfactual module in a reproducible way.
- 2026-02-05: Wired dependency on W0 counterfactual-assumptions lock (T098) to prevent runtime blocking/assumption drift.
- 2026-02-05: Updated per feedback (2026-02-01): added explicit sample/full interfaces, committed sample artifacts for CI determinism, and required machine-readable metadata (assumptions + panel/manifest hashes).


- 2026-02-06: Planner reconciliation — outputs already exist in repo; moved state to ready_for_review to clear control-plane drift before unattended fullscale preflight.


- 2026-02-06: Judge approval — promoted to done after repo-level gate/test/preflight checks and output existence verification to unblock downstream dependencies.
