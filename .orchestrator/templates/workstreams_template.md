# Workstreams (template)

Workstreams are how we prevent agent clashes: each workstream has **explicit ownership** of paths and artifacts.

## Workstreams table

| Workstream | Purpose | Owns paths | Does NOT own | Outputs (examples) | Gate(s) |
|---|---|---|---|---|---|
| W0 Protocol/Contracts | Canonical definitions + contracts | `docs/protocol.md`, `contracts/` | `src/`, `registry/` | locked protocol + schemas | `make gate` |
| W1 Data: off-chain | External sources ETL | `src/etl/offchain/`, `data/raw/<source>/`, `data/raw_manifest/<source>_`, `data/processed/<source>/`, `data/samples/<source>/` | `docs/protocol.md`, `contracts/`, `registry/`, `src/analysis/` | snapshots + manifests + processed tables (not committed) | `make gate` |
| W2 Data: on-chain | Ethereum L1 extraction + attribution-ready tables | `src/etl/onchain/`, `data/raw/l1/`, `data/raw_manifest/l1_`, `data/processed/l1/`, `data/samples/l1/` | `docs/protocol.md`, `contracts/`, `registry/`, `src/analysis/` | L1 extracts + manifests + processed tables (not committed) | `make gate` |
| W3 Registry | Attribution mapping | `registry/` | `docs/protocol.md`, `src/etl/` | registry CSV/JSON | `make gate` |
| W4 Metrics | Metric construction + tests | `src/analysis/metrics*`, `tests/` | `src/etl/` | metric modules + tests | `make gate` |
| W5 Validation | Reconciliation + tolerances | `src/validation/`, `reports/validation/` | `src/etl/` | validation reports | `make gate` |
| W6 Analysis | Figures + econometrics | `src/analysis/`, `reports/figures/` | `src/etl/`, `src/analysis/metrics*` | figures/tables | `make gate` |
| W7 Writing | Paper/deck/notes | `docs/` (except protocol), `reports/paper/` | `docs/protocol.md`, `src/` | narrative drafts | `make gate` |
| W8 Ops/Automation | Gates + environment + runbooks | `scripts/`, `.devcontainer/`, `.github/workflows/`, `Makefile`, `docs/runbook_swarm*.md` | `docs/protocol.md`, `contracts/`, `registry/` | deterministic gates + automation docs | `make gate` |
| W9 Data Products | Build analysis-ready datasets | `src/etl/panel_*`, `data/processed/panels/`, `data/processed_manifest/`, `data/samples/panels/` | `docs/protocol.md`, `contracts/`, `registry/` | analysis-ready builds + manifests | `make gate` |

## Notes

- Keep “Owns paths” strict; propose cross-cutting changes via PR and explicit review.
- Prefer parallelism only when interfaces (schemas, function signatures, output paths) are locked.
