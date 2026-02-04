# STR empirical tests (sample)

## Inputs
- Panel: `data/samples/panels/daily_rollup_panel_v1_sample.csv`
- Panel sha256: `437ff47d9cf908ac9d234b21697b28faedaa4062a8ddc11098f83096ec7e3065`
- Dencun boundary (UTC): `2024-03-13`

## Summary (ecosystem STR)
- Mean STR (pre): 0.2719
- Mean STR (post): 0.1311
- Min/Max STR: 0.1307 / 0.2729

## Tests
- Mann–Kendall tau: -0.5927, p≈5.109e-08
- NW trend slope (STR/day): -0.005128 (se 0.000524), p≈0
- Break (mean shift at Dencun): -0.1408 (se 0.0001), p≈0
- Break (post slope change): -0.000002 (se 0.000013), p≈0.8874
- Elasticity log(rent)~log(fees): 1.203 (se 0.033), p≈0

## Outputs
- `reports/tables/str_empirical_tests_sample.json`
- `reports/tables/str_empirical_tests_sample.md`
- `reports/tables/str_time_series_sample.csv`
- `reports/figures/str_time_series_sample.svg`
- `reports/tables/str_empirical_tests_sample_run.json` (run manifest)

Notes:
- P-values are normal approximations (see JSON for details).
