# `data/samples/growthepie/` — growthepie endpoint notes + sample conventions

growthepie is the **primary** data source for the STR denominator (`l2_fees_eth`) and a useful
secondary vendor series for `rent_paid_eth/profit_eth` (triangulation only for rent).

## Endpoints (public)

- Master catalog: `https://api.growthepie.com/v1/master.json`
- Export time series: `https://api.growthepie.com/v1/export/{metric_key}.json`

## Metric key discipline

Do **not** hardcode metric keys without recording the selection.

Workflow:
1) Snapshot `master.json` (append-only) and record a raw manifest.
2) Select the exact `metric_key` values for:
   - fees (ETH-native preferred): `l2_fees_eth` target
   - rent paid (vendor): `rent_paid_eth` candidate
   - profit (vendor): `profit_eth` (identity check only)
   - txcount: `txcount`
3) Record chosen keys + units in the ETL notes and in any sample README.

## Required sample output columns (golden sample)

When committing a sample panel CSV for tests, target columns:

- `date_utc`
- `rollup_id`
- `l2_fees_eth`
- `rent_paid_eth` (vendor series; label clearly as vendor if used)
- `profit_eth` (optional)
- `txcount` (optional)

## Repro commands (expected once ETL exists)

```bash
python src/etl/growthepie_fetch.py --run-date YYYY-MM-DD
python scripts/make_raw_manifest.py growthepie data/raw/growthepie/YYYY-MM-DD --as-of YYYY-MM-DD -- \
  python src/etl/growthepie_fetch.py --run-date YYYY-MM-DD
```
