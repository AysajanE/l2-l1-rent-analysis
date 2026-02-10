---
task_id: T086
title: "Issuance ETL: ingest daily ETH issuance series + golden sample"
workstream: W1
role: Worker
priority: medium
dependencies:
  - "T096"
  - "T097"
parallel_ok: true
allowed_paths:
  - "src/etl/issuance_fetch.py"
  - "data/raw/issuance/"
  - "data/raw_manifest/issuance_"
  - "data/processed/issuance/"
  - "data/processed_manifest/issuance_"
  - "data/samples/issuance/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/analysis/"
  - "src/validation/"
outputs:
  - "src/etl/issuance_fetch.py"
  - "data/raw/issuance/YYYY-MM-DD/..."
  - "data/raw_manifest/issuance_YYYY-MM-DD.json"
  - "data/processed/issuance/issuance_daily.parquet"
  - "data/processed_manifest/issuance_daily_YYYY-MM-DD.json"
  - "data/samples/issuance/issuance_daily_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Need API credentials"
---

# Task T086 — Issuance ETL: ingest daily ETH issuance series + golden sample

## Context

For “burn vs issuance” style outputs and related interpretation, we need a daily ETH issuance series with documented provenance.

**Issuance definition is locked in W0** (see T097 + `contracts/schemas/issuance_daily_v1.yaml` + `contracts/decisions.md`); this W1 task must implement the ETL deterministically against that contract (no new definition choices here).

## Inputs

- Locked definition + schema (read-only):
  - `docs/protocol.md` (issuance definition + source policy)
  - `contracts/schemas/issuance_daily_v1.yaml`
  - `contracts/decisions.md` (issuance decision entry)
- Sources (per W0 decision; do not substitute without `@human`):
  - Primary: `ultrasound.money` daily issuance series (snapshotted)
  - Secondary: beacon-chain explorer / consensus feed for tolerance checks

## Outputs

- ETL code: `src/etl/issuance_fetch.py`
- Raw snapshots (append-only): `data/raw/issuance/<YYYY-MM-DD>/...`
- Raw manifest (tracked): `data/raw_manifest/issuance_<YYYY-MM-DD>.json`
- Normalized issuance table (not committed): `data/processed/issuance/issuance_daily.parquet`
  - Must conform to `contracts/schemas/issuance_daily_v1.yaml` (include `date_utc`, `issuance_eth`, `source`, optional `method`).
- Processed manifest (tracked): `data/processed_manifest/issuance_daily_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/issuance/issuance_daily_sample.csv`
  - Prefer the repo’s canonical sample window (see `data/samples/README.md`) so the enriched panel v2 sample can join deterministically.

## Success Criteria

- [ ] Output conforms to `contracts/schemas/issuance_daily_v1.yaml` (daily UTC grain; `issuance_eth` in ETH; `source` set consistently)
- [ ] Raw manifest exists and is append-only
- [ ] Normalized table schema is asserted against `contracts/schemas/issuance_daily_v1.yaml` (fail fast on missing/invalid columns)
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` and includes input manifests + output hashes
- [ ] Golden sample is committed and stable
- [ ] `make gate` passes

## Status
- State: done
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-01-30: Task created (Planner); issuance is needed for “burn vs issuance” context and counterfactual framing.
- 2026-02-05: Wired dependency on W0 issuance-definition lock (T097); W1 ETL must implement the locked `issuance_daily_v1` contract.


- 2026-02-10: Claimed by swarm runner; starting worker (branch: T086_issuance_etl_daily_and_sample).

- 2026-02-10: Implemented full ETL workflow in `src/etl/issuance_fetch.py` with:
  - deterministic `--sample` mode (canonical window) and stable sample writer,
  - snapshot fetch/reuse to `data/raw/issuance/<YYYY-MM-DD>/...` from ultrasound endpoints,
  - strict contract assertion against `contracts/schemas/issuance_daily_v1.yaml`,
  - parquet output writer for `data/processed/issuance/issuance_daily.parquet`,
  - raw/processed manifest generation via `scripts/make_raw_manifest.py` and `scripts/make_processed_manifest.py`,
  - explicit guarded proxy mode (`--allow-net-from-supply-over-time`) rather than silent source-definition drift.

- 2026-02-10: Reproduction command used:
  - `PYTHONPATH=/tmp/pydeps python src/etl/issuance_fetch.py --run-date 2026-02-10 --input-csv data/samples/issuance/issuance_daily_sample.csv --write-raw-manifest --write-processed-manifest --write-sample`
  - Produced:
    - `data/raw/issuance/2026-02-10/...` (append-only raw snapshots),
    - `data/raw_manifest/issuance_2026-02-10.json`,
    - `data/processed/issuance/issuance_daily.parquet`,
    - `data/processed_manifest/issuance_daily_2026-02-10.json`,
    - `data/samples/issuance/issuance_daily_sample.csv` (stable/reused).

- 2026-02-10: Gate/test results:
  - `make test` passed (`Ran 41 tests`, `OK`).
  - `make gate` failed on unrelated pre-existing `processed_manifest_consistency` missing outputs outside T086 `allowed_paths`:
    - `data/processed/panels/daily_rollup_panel_v1_sample.csv`
    - `data/processed/l2beat/l2beat_costs_daily.parquet`
    - `data/processed/onchain/rollup_costs_daily.csv`
    - `data/processed/onchain/rollup_costs_decomposition_daily.csv`

- 2026-02-10: `@human` unblock required: either restore/regenerate the unrelated processed artifacts above in their owning tasks/worktrees, or run `make gate` in an environment where those referenced outputs exist.


- 2026-02-10: Judge: gates ok; ownership ok. Review log: /tmp/swarm-worktrees/wt-T086/data/tmp/swarm_logs/T086_20260210T005110Z_judge_review.txt
