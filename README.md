# L2–L1 Rent Analysis (Ethereum)

This repo contains an empirical research project measuring Ethereum L1’s “take rate” on rollup economics: how much rollups pay Ethereum L1 (“rent”) relative to the fees they collect from L2 users.

## Primary metric: Settlement Take Rate (STR)

For day *t* (UTC):

`STR_t = (Σ_i RentPaid_{i,t}) / (Σ_i L2Fees_{i,t})`

Canonical definitions, units, regimes, source priority, tolerances, and edge-case rules are locked in `docs/protocol.md`.

## Research goals

- Trend STR over time (2022-01-01 → present).
- Explain mechanisms via decomposition (burn vs tips; blob vs execution; pre-/post-Dencun).
- Evaluate policy counterfactuals (e.g., blob-fee floor/reserve mechanism such as EIP-7918).

## Data sources (priority)

When sources disagree for the same concept, the protocol prioritizes:

1. On-chain computed Ethereum L1 costs (authoritative for `RentPaid` and decomposition).
2. growthepie exports (primary for `L2Fees`; secondary vendor `rent_paid/profit` series for triangulation).
3. L2BEAT costs series (triangulation / sanity check).

On-chain rent computation is supported via **BigQuery public Ethereum tables** (preferred for unattended runs) and an RPC-based fallback path.

Blobscan may be used for blob-market aggregates and cross-checks when available.

## Repo structure

- `docs/` — research plan + runbooks; **protocol lock**: `docs/protocol.md`
- `contracts/` — canonical schemas + data dictionary (e.g., `contracts/schemas/panel_schema_str_v1.yaml`)
- `registry/` — rollup universe + attribution evidence (`registry/rollup_registry_v1.csv`)
- `src/etl/` — ingestion/extraction code (networked; must snapshot inputs)
- `src/validation/` — deterministic checks (no network)
- `src/analysis/` — deterministic figures/tables (no network)
- `data/raw/` and `data/processed/` — gitignored large artifacts; provenance tracked in `data/raw_manifest/` and `data/processed_manifest/`
- `reports/` — generated research outputs (validation, figures, tables, status, paper, deck)

## Repro / quality gates

```bash
make gate
make test
```

## Project workflow (tasks)

Work is organized as explicit tasks under `.orchestrator/` with ownership boundaries to support parallel execution. For operational guidance, see `docs/runbook_swarm.md` and `docs/runbook_swarm_automation.md`.
