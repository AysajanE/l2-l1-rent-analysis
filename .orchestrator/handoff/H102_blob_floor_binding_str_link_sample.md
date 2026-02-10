# Handoff H102 — Blob Floor-Binding and STR Link (Sample)

## Summary (1–3 sentences)

Added a deterministic, stdlib-only analysis script that computes the protocol-locked blob “at-minimum” indicator (integer-safe wei logic) and derives the >=7-day contiguous floor-binding regime flag, then links those indicators to daily ecosystem STR on the committed v2 sample panel.

## What changed / what exists now

- Files/paths:
  - `src/analysis/blob_floor_binding_str_link.py`
- Outputs produced:
  - `reports/tables/blob_floor_binding_str_link_sample.csv`
  - `reports/figures/blob_floor_binding_str_link_sample.svg`
  - `reports/tables/blob_floor_binding_str_link_sample_run.json` (inputs/outputs + hashes + parameters)

## How to reproduce / verify

- Commands:
  - `python src/analysis/blob_floor_binding_str_link.py --sample`
  - `make gate`
  - `make test`
- Expected results:
  - The script writes the stable sample artifacts above and prints a JSON summary to stdout.

## Assumptions / risks

- Regime logic follows `docs/protocol.md`: post-Dencun only, threshold is `floor(1.05 * min_post)` implemented as `(min_post * 105)//100` in wei (no floating-point gwei in regime classification).
- The sample panel’s post-Dencun blob base fee alternates such that there are no >=7-day contiguous “at-minimum” runs; `is_floor_binding_regime_7d` is 0 for all sample days.

## Open questions / next steps

- If downstream work needs a non-zero floor-binding regime in sample mode, update the v2 sample generator (W9) to include a contiguous >=7-day at-minimum run; otherwise expect the regime flag to remain 0 in sample artifacts.
- For full runs: `python src/analysis/blob_floor_binding_str_link.py --panel <path> --tag full`.
