# Workstreams (template)

Workstreams are how we prevent agent clashes: each workstream has **explicit ownership** of paths and artifacts.

## Workstreams table

| Workstream | Purpose | Owns paths | Does NOT own | Outputs (examples) | Gate(s) |
|---|---|---|---|---|---|
| W0 Protocol | Definitions + inclusion criteria | `docs/protocol.md` | everything else | locked definitions | `make gate` |
| W1 Data: off-chain | External sources ETL | `src/etl/` | `src/analysis/` | normalized tables | data validation |
| W2 Data: on-chain | L1 extraction | `src/etl/` | `docs/` | on-chain tables | data validation |
| W3 Registry | Attribution mapping | `data/schemas/` | `src/etl/` | registry CSV/JSON | schema checks |
| W4 Metrics | Metric construction + tests | `src/analysis/` | `src/etl/` | metric module + tests | unit tests |
| W5 Validation | Reconciliation + error bands | `src/validation/` | `src/analysis/` | validation report | `make gate` |
| W6 Analysis | Econometrics + figures | `src/analysis/` | `src/etl/` | figures/tables | notebook checks |
| W7 Writing | Paper/deck | `docs/` | code paths | report draft | link checks |

## Notes

- Keep “Owns paths” strict; propose cross-cutting changes via PR and explicit review.
- Prefer parallelism only when interfaces (schemas, function signatures, output paths) are locked.
