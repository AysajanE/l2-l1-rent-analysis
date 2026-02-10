---
task_id: T090
title: "Data product: build enriched daily panel (contract v2) + sample + manifest"
workstream: W9
role: Worker
priority: medium
dependencies:
  - "T096"
  - "T080"
  - "T084"
  - "T085"
  - "T086"
  - "T089"
parallel_ok: false
allowed_paths:
  - "src/etl/panel_build_daily_rollup_panel_v2.py"
  - "data/processed/panels/"
  - "data/processed_manifest/daily_rollup_panel_"
  - "data/samples/panels/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "data/raw/"
outputs:
  - "src/etl/panel_build_daily_rollup_panel_v2.py"
  - "data/processed/panels/daily_rollup_panel_v2.parquet"
  - "data/processed_manifest/daily_rollup_panel_v2_YYYY-MM-DD.json"
  - "data/samples/panels/daily_rollup_panel_v2_sample.csv"
gates:
  - "make gate"
stop_conditions:
  - "Missing upstream processed inputs"
  - "Contract mismatch (block)"
---

# Task T090 — Data product: build enriched daily panel (contract v2) + sample + manifest

## Context

Beyond the STR-minimum dataset (v1), full-scale research requires an enriched panel that includes regime variables and macro inputs. The enriched schema must be locked first (T080).

This task builds the **contract v2** panel by extending the v1 panel (T089) with:
- blob regime variables (T084),
- ETH/USD prices (T085),
- ETH issuance (T086),
and any other enrichment explicitly defined in the v2 contract.

## Inputs

- `contracts/schemas/panel_schema_str_v2.yaml` (read-only; produced by T080)
- `data/processed/panels/daily_rollup_panel_v1.parquet` (read-only; produced by T089)
- Processed blobscan, prices, issuance tables from T084/T085/T086 (read-only)

## Outputs

- Build script: `src/etl/panel_build_daily_rollup_panel_v2.py`
  - Deterministic; no network calls.
- Enriched panel (not committed): `data/processed/panels/daily_rollup_panel_v2.parquet`
- Processed manifest (tracked): `data/processed_manifest/daily_rollup_panel_v2_<YYYY-MM-DD>.json`
- Golden sample (tracked): `data/samples/panels/daily_rollup_panel_v2_sample.csv`
  - Prefer the repo’s canonical sample window + rollup subset (see `data/samples/README.md`) unless explicitly blocked.

## Success Criteria

- [ ] Output conforms to the v2 contract (field list + units + nullability)
- [ ] Output schema is asserted against `contracts/schemas/panel_schema_str_v2.yaml` (fail fast on missing/invalid columns)
- [ ] Join semantics are explicit and deterministic (document in code and manifest)
- [ ] Processed manifest is generated via `python scripts/make_processed_manifest.py ...` (append-only; includes input manifests + output hashes)
- [ ] Golden sample is committed and stable
- [ ] `make gate` passes

## Status
- State: blocked
- Last updated: 2026-02-10
## Notes / Decisions

- 2026-01-30: Task created (Planner) to produce the enriched dataset used for regime + counterfactual analysis.


- 2026-02-10: Claimed by swarm runner; starting worker (branch: T090_panel_build_daily_rollup_panel_v2_enriched).

- 2026-02-10: Implemented v2 builder hardening in `src/etl/panel_build_daily_rollup_panel_v2.py`.
  - Added contract-aware table loading for CSV and `.parquet` paths (with CSV fallback for `.parquet` filenames).
  - Added deterministic join metadata (key mode, matched/unmatched/assigned counts, conflict policy) and output-format metadata.
  - Added processed-manifest support (`--write-manifest`, `--as-of`, `--manifest-*`) using `scripts/make_processed_manifest.py`.
  - Added sample controls (`--write-sample`, `--sample-out`) and pinned default sample-mode inputs to the tracked v2 sample fixture for stable CI behavior.
  - Full-mode defaults now resolve expected processed input candidates (`daily_rollup_panel_v1`, on-chain decomposition, blobscan, prices, issuance) when available.

- 2026-02-10: Produced sample-mode artifacts and validated reproducibility.
  - Command:
    - `python src/etl/panel_build_daily_rollup_panel_v2.py --sample --write-sample --write-manifest --as-of 2026-02-10 --manifest-inputs data/processed_manifest/daily_rollup_panel_v1_sample_2026-02-10.json data/processed_manifest/blobscan_daily_2026-02-10.json data/processed_manifest/prices_daily_2026-02-10.json data/processed_manifest/issuance_daily_2026-02-10.json`
  - Outputs:
    - `data/processed/panels/daily_rollup_panel_v2_sample.csv` (untracked runtime artifact)
    - `data/processed_manifest/daily_rollup_panel_v2_sample_2026-02-10.json` (tracked)
    - `data/samples/panels/daily_rollup_panel_v2_sample.csv` (rewritten deterministically; no content change)

- 2026-02-10: Gates/tests run.
  - `make gate` => pass
  - `make test` => pass (`Ran 46 tests`)

- 2026-02-10: `@human` stop condition hit (`Missing upstream processed inputs`) for full-mode v2 output/manifest.
  - Full-mode command attempted:
    - `python src/etl/panel_build_daily_rollup_panel_v2.py --panel-v1-csv data/processed/panels/daily_rollup_panel_v1.parquet --decomposition-csv data/processed/onchain/rollup_costs_decomposition_daily.csv --l1-regime-csv data/processed/blobscan/blobscan_daily.parquet --prices-csv data/processed/prices/prices_daily.parquet --issuance-csv data/processed/issuance/issuance_daily.parquet --out data/processed/panels/daily_rollup_panel_v2.parquet`
  - Missing in this worktree: `data/processed/panels/daily_rollup_panel_v1.parquet` and upstream processed enrichments under `data/processed/{onchain,blobscan,prices,issuance}/`.
  - Decision needed: provide/regenerate these upstream processed inputs in-branch (or explicitly permit alternate full-mode input paths) to unblock `daily_rollup_panel_v2.parquet` + `daily_rollup_panel_v2_<YYYY-MM-DD>.json`.


- 2026-02-10: @human Judge blocked: path_ownership_violation. Review log: /tmp/swarm-worktrees/wt-T090/data/tmp/swarm_logs/T090_20260210T110224Z_judge_review.txt
