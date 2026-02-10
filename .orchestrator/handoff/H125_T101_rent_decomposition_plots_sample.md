# Handoff H125 — T101 rent decomposition sample artifacts

## Summary (1–3 sentences)

T101 adds a deterministic, offline analysis script that aggregates daily rent decomposition components from the committed v2 sample panel and renders a shares-over-time SVG. Sample-mode outputs are written to stable `reports/` paths and include a run manifest with hashes for traceability.

## What changed / what exists now

- Files/paths:
  - `src/analysis/plot_rent_decomposition.py`
- Outputs produced (sample mode):
  - `reports/tables/rent_decomposition_sample.csv`
  - `reports/figures/rent_decomposition_sample.svg`
  - `reports/tables/rent_decomposition_sample_run.json`

## How to reproduce / verify

- Commands:
  - `python src/analysis/plot_rent_decomposition.py --sample`
  - `make gate`
  - `make test`
- Expected results:
  - The command prints a JSON `{"ok": true, ...}` payload and rewrites the 3 sample outputs above.
  - `make gate` and `make test` pass.

## Assumptions / risks

- The sample fixture currently has `rent_base_fee_burn_eth` and `rent_priority_fee_eth` empty (coverage recorded in the run manifest). The script treats missing decomposition components as `0` for aggregation and exposes an `unattributed` residual, so sample-mode “burn vs tips” is effectively limited by what is populated in the sample panel.

## Open questions / next steps

- If we want the sample plot to show a meaningful burn-vs-tips split, update the v2 sample fixture upstream (T090 or a new W9 task) to include non-empty `rent_base_fee_burn_eth` and `rent_priority_fee_eth` fields.

