# Settlement Take Rate (STR) — Draft (W7)

This is a working manuscript skeleton for the L2→L1 rent capture project.

## Scope and governance

- Canonical definitions and inclusion rules: `docs/protocol.md`
- Panel schema (v1): `contracts/schemas/panel_schema_str_v1.yaml`
- Rollup universe registry: `registry/rollup_registry_v1.csv`

This draft references only repo-present artifacts and is intended to be expanded as processed datasets land.

## 1. Research question

1) What is Ethereum’s **Settlement Take Rate (STR)** over time?
2) Did STR change materially around the Dencun/EIP‑4844 regime boundary (protocol boundary: `2024-03-13` UTC)?
3) How elastic is L1 rent paid with respect to L2 activity/scale (fees/transactions), controlling for regime shifts?

## 2. Data (current state)

### 2.1 Panel (v1)

- Required fields: `date_utc, rollup_id, l2_fees_eth, rent_paid_eth`
- Optional fields: `profit_eth, txcount`

Sample-mode artifact used for CI/determinism checks:
- `data/samples/panels/daily_rollup_panel_v1_sample.csv` (synthetic; spans Dencun boundary)

### 2.2 Provenance

- Sample panel build manifest:
  - `data/processed_manifest/daily_rollup_panel_v1_sample_2026-02-04.json`

## 3. Methods (empirical tests)

Core hypothesis tests recommended for swarm safety are implemented with `--sample` mode:

- Mann–Kendall trend test on daily ecosystem STR
- Newey–West trend regression on daily ecosystem STR
- Structural break regressions at the Dencun boundary (mean shift; slope change)
- Elasticity regression (log‑log), using daily aggregates and controls

Implementation (sample-mode outputs committed for determinism):
- Script: `src/analysis/str_empirical_tests.py`
- Outputs:
  - `reports/tables/str_empirical_tests_sample.json`
  - `reports/tables/str_empirical_tests_sample.md`
  - `reports/tables/str_time_series_sample.csv`
  - `reports/figures/str_time_series_sample.svg`

## 4. Results (sample-mode placeholder)

These results are generated from a **synthetic** sample dataset and exist to validate the research automation pipeline.
Replace with full-panel results once `data/processed/panels/daily_rollup_panel_v1.csv` (or v2) is built.

- Summary + tests: `reports/tables/str_empirical_tests_sample.md`
- Time series figure: `reports/figures/str_time_series_sample.svg`

## 5. Robustness and extensions (planned)

Once v2 panels and on-chain decompositions are available, extend the analysis to:

- burn vs tips decomposition over time
- blob vs execution burn decomposition
- blob fee “at-minimum” regime classification and correlation with STR
- issuance/burn share context series (see protocol lock for issuance definition)

## 6. Reproduction

```bash
make gate
make test

# Build the sample panel output + processed manifest (writes into gitignored data/processed/)
python src/etl/panel_build_daily_rollup_panel_v1.py --sample --write-manifest --as-of 2026-02-04

# Generate sample-mode empirical outputs (writes into reports/)
python src/analysis/str_empirical_tests.py --sample
```

