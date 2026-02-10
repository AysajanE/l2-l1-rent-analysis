# H083 — L2BEAT ETL costs daily + sample

## Summary

Implemented T083 deliverables in `src/etl/l2beat_fetch.py` and generated the requested L2BEAT artifacts for run-date `2026-02-10`.

## Files changed

- `src/etl/l2beat_fetch.py`
- `data/samples/l2beat/README.md`
- `data/raw_manifest/l2beat_2026-02-10.json`
- `data/processed_manifest/l2beat_costs_daily_2026-02-10.json`
- `data/samples/l2beat/l2beat_costs_daily_sample.csv`
- `.orchestrator/backlog/T083_l2beat_etl_costs_daily_and_sample.md` (Status + Notes only)

## Runtime artifacts produced (not tracked)

- `data/raw/l2beat/2026-02-10/...`
- `data/processed/l2beat/l2beat_costs_daily.parquet`

## Reproduction commands

```bash
# discovery
python src/etl/l2beat_fetch.py --discover

# full run (requires pyarrow in Python path/environment)
PYTHONPATH=/tmp/pydeps python src/etl/l2beat_fetch.py \
  --run-date 2026-02-10 \
  --start-date 2022-01-01 \
  --end-date 2026-02-10 \
  --filter-type rollups \
  --write-raw-manifest \
  --write-processed-manifest \
  --write-sample
```

## Gate/test commands and outcomes

- `make test` -> **PASS** (`Ran 41 tests`, `OK`)
- `make gate` -> **FAIL** (unrelated pre-existing processed manifest outputs missing in this worktree):
  - `data/processed/panels/daily_rollup_panel_v1_sample.csv`
  - `data/processed/onchain/rollup_costs_daily.csv`
  - `data/processed/onchain/rollup_costs_decomposition_daily.csv`

## Assumptions and limitations

- Parquet output requires `pyarrow`; environment did not have it preinstalled.
- L2BEAT `costs.table` (filter `rollups`) returned no keys for `metis` and `taiko`; these are recorded under processed-manifest meta (`missing_from_table_slugs`) and therefore excluded from normalized output.
- `make gate` cannot be made green within T083 `allowed_paths` because missing files are outside scope.

## Requested unblock (`@human`)

Decide one of:
1. Provide/restore the unrelated `data/processed/onchain/*` and `data/processed/panels/*` runtime outputs in this worktree before running `make gate`, or
2. run `make gate` in a branch/worktree where git diff base resolution works (so unchanged historical volatile manifest outputs are skipped as intended), or
3. explicitly permit T083 worker to regenerate those unrelated outputs outside current `allowed_paths`.
