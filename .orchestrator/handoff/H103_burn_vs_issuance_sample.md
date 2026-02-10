# Handoff H103 — Burn vs Issuance Sample Time Series (T103)

## Summary (1–3 sentences)

T103 adds a deterministic, offline analysis script to combine gross ETH issuance (W0-locked definition) with rollup-attributed burn components from the v2 daily rollup panel sample, and commits a stable sample CSV+SVG with a run manifest.

## What changed / what exists now

- Files/paths:
  - `src/analysis/plot_burn_vs_issuance.py`
- Outputs produced (sample tag):
  - `reports/tables/burn_vs_issuance_sample.csv`
  - `reports/figures/burn_vs_issuance_sample.svg`
  - `reports/tables/burn_vs_issuance_sample_run.json`

## How to reproduce / verify

- Commands:
  - `python src/analysis/plot_burn_vs_issuance.py`
  - `make gate`
- Expected results:
  - The three sample outputs above are written/updated.
  - Re-running the script yields identical bytes for `burn_vs_issuance_sample.csv` and `burn_vs_issuance_sample.svg` for the committed sample inputs (the `_run.json` will update its timestamp).

## Assumptions / risks

- Issuance is sourced from `data/samples/issuance/issuance_daily_sample.csv` in sample mode (gross consensus-layer issuance; not net of burn).
- Burn series is **rollup-attributed**: sums of panel fields `rent_base_fee_burn_eth` + `rent_blob_fee_burn_eth`; it is not total Ethereum burn and should not be interpreted as network-wide “net issuance”.
- In the committed v2 panel sample, `rent_base_fee_burn_eth` is empty (so base burn aggregates are 0 in the sample artifacts).

## Open questions / next steps

- If/when `daily_rollup_panel_v2` is enriched with non-empty `rent_base_fee_burn_eth` in sample/full panels, the same script/table will automatically reflect it.

