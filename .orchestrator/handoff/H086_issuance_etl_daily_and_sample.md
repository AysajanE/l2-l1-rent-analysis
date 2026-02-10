# H086 — Issuance ETL daily + sample

## Summary

Implemented T086 ETL deliverables in `src/etl/issuance_fetch.py`: append-only raw snapshots, contract-asserted normalization, parquet output, and manifest generation. Generated the required issuance artifacts for as-of date `2026-02-10`.

## Files changed

- `src/etl/issuance_fetch.py`
- `data/raw_manifest/issuance_2026-02-10.json`
- `data/processed_manifest/issuance_daily_2026-02-10.json`
- `.orchestrator/backlog/T086_issuance_etl_daily_and_sample.md` (Status + Notes only)

## Runtime artifacts produced (not tracked)

- `data/raw/issuance/2026-02-10/...`
- `data/processed/issuance/issuance_daily.parquet`

## Reproduction commands

```bash
# sample-mode stability check
python src/etl/issuance_fetch.py --sample

# full T086 run (pyarrow available via /tmp/pydeps in this environment)
PYTHONPATH=/tmp/pydeps python src/etl/issuance_fetch.py \
  --run-date 2026-02-10 \
  --input-csv data/samples/issuance/issuance_daily_sample.csv \
  --write-raw-manifest \
  --write-processed-manifest \
  --write-sample
```

## Gate/test commands and outcomes

- `make test` -> **PASS** (`Ran 41 tests`, `OK`)
- `make gate` -> **FAIL** (unrelated pre-existing `processed_manifest_consistency` outputs missing)
  - `data/processed/panels/daily_rollup_panel_v1_sample.csv`
  - `data/processed/l2beat/l2beat_costs_daily.parquet`
  - `data/processed/onchain/rollup_costs_daily.csv`
  - `data/processed/onchain/rollup_costs_decomposition_daily.csv`

## Assumptions and limitations

- Ultrasound endpoint `https://ultrasound.money/api/v2/fees/supply-dashboard-analysis` returned HTTP 503 during this run; this is captured in manifest meta.
- To avoid silent definition drift, the ETL does **not** silently infer gross issuance from unsupported payloads. A proxy fallback is available only with explicit opt-in: `--allow-net-from-supply-over-time`.
- This task could not make `make gate` green without touching out-of-scope paths per T086 `allowed_paths`.

## @human unblock needed

Choose one:
1. Restore/regenerate the unrelated processed artifacts referenced by existing manifests, or
2. run `make gate` in a worktree/environment where those outputs already exist.
