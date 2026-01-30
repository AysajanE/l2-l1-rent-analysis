# Workstreams (project coordination)

Workstreams define ownership boundaries so agents can work in parallel safely.

This is an initial, project-specific set. Refine as the pipeline grows.

## Workstreams table

| Workstream | Purpose | Owns paths | Does NOT own | Outputs (examples) | Gate(s) |
|---|---|---|---|---|---|
| W0 Protocol/Contracts | Canonical definitions, regimes, tolerances, specs | `docs/protocol.md`, `contracts/` | `src/`, `registry/`, `data/raw/`, `data/processed/` | Locked protocol + canonical contracts | `make gate` |
| W1 Data: off-chain | Ingest off-chain sources (APIs/dashboards) | `src/etl/offchain/`, `src/etl/growthepie_*`, `src/etl/l2beat_*`, `src/etl/blobscan_*`, `src/etl/prices_*`, `src/etl/issuance_*`, `data/raw/growthepie/`, `data/raw/l2beat/`, `data/raw/blobscan/`, `data/raw/prices/`, `data/raw/issuance/`, `data/raw_manifest/growthepie_`, `data/raw_manifest/l2beat_`, `data/raw_manifest/blobscan_`, `data/raw_manifest/prices_`, `data/raw_manifest/issuance_`, `data/processed/growthepie/`, `data/processed/l2beat/`, `data/processed/blobscan/`, `data/processed/prices/`, `data/processed/issuance/`, `data/processed_manifest/growthepie_`, `data/processed_manifest/l2beat_`, `data/processed_manifest/blobscan_`, `data/processed_manifest/prices_`, `data/processed_manifest/issuance_`, `data/samples/growthepie/`, `data/samples/l2beat/`, `data/samples/blobscan/`, `data/samples/prices/`, `data/samples/issuance/` | `docs/protocol.md`, `contracts/`, `registry/`, `src/analysis/`, `src/validation/` | Raw snapshots (append-only); tracked raw manifests; processed source tables (not committed); small golden samples (tracked) | `make gate` |
| W2 Data: on-chain | Extract Ethereum L1 data + compute rollup-attributed costs/decomposition | `src/etl/onchain/`, `src/etl/l1_*`, `src/etl/rpc_*`, `data/raw/l1/`, `data/raw_manifest/l1_`, `data/processed/l1/`, `data/processed/onchain/`, `data/processed_manifest/l1_`, `data/processed_manifest/onchain_`, `data/samples/l1/` | `docs/protocol.md`, `contracts/`, `registry/`, `src/analysis/`, `src/validation/` | Raw L1 extracts (append-only); tracked raw manifests; processed on-chain tables (not committed); small samples (tracked) | `make gate` |
| W3 Registry | Attribution registries (rollups/addresses/labels) | `registry/` | `docs/protocol.md`, `contracts/`, `src/etl/` | Versioned registries + `registry/CHANGELOG.md` | `make gate` |
| W4 Metrics | Metric construction + unit tests | `src/analysis/metrics*`, `tests/` | `src/etl/`, `docs/protocol.md` | Metric module(s) + tests | `make gate` |
| W5 Validation | Reconciliation and sanity checks | `src/validation/`, `reports/validation/` | `src/etl/`, `docs/protocol.md` | Validation reports (MD/JSON) | `make gate` |
| W6 Analysis | Econometrics/figures built from processed data | `src/analysis/`, `reports/figures/`, `reports/tables/` | `src/etl/`, `docs/protocol.md`, `src/analysis/metrics*` | Figures + analysis scripts | `make gate` |
| W7 Writing | Narrative outputs (paper/deck/notes) | `docs/` (except `docs/protocol.md`), `reports/paper/`, `reports/deck/` | `docs/protocol.md`, `contracts/`, `src/` | Draft writeups and figure/table references | `make gate` |
| W8 Ops/Automation | Swarm automation, gates, environment/runbooks | `scripts/`, `.devcontainer/`, `.github/workflows/`, `Makefile`, `pyproject.toml`, `.python-version`, `docs/runbook_swarm*.md` | `docs/protocol.md`, `contracts/`, `registry/`, `data/raw/` | Swarm runner improvements; deterministic gates; operational runbooks | `make gate` |
| W9 Data Products | Build analysis-ready datasets + manifests | `src/etl/panel_*`, `data/processed/panels/`, `data/processed_manifest/panel_`, `data/processed_manifest/daily_rollup_panel_`, `data/samples/panels/` | `docs/protocol.md`, `contracts/`, `registry/`, `data/raw/` | Analysis-ready dataset builds (not committed); processed manifests (tracked); small panel samples (tracked) | `make gate` |

## Ownership rules

- If a task needs to edit outside its workstream ownership, it must:
  1) add an `@human` note in the task file, and
  2) be re-scoped or split into multiple tasks with clear ownership.

## Concurrency notes (swarm)

- The swarm enforces simple workstream-level concurrency. For safe parallelism inside a workstream, tasks should:
  - declare narrow `allowed_paths`, and
  - set `parallel_ok: true` only when those paths are disjoint from other active tasks.
