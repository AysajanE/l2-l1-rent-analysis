# L2–L1 Rent Analysis (Ethereum)

Empirical research repository for measuring how much of rollup economics is captured by Ethereum Layer 1.

The central object in this project is **Settlement Take Rate (STR)**: the share of rollup user fees that ultimately becomes Ethereum L1 rent. This repo is organized as a protocol-locked research system rather than an ad hoc notebook collection, so metric definitions, source priority, units, tolerances, and edge cases stay auditable over time.

## Core metric

For day `t` in UTC:

`STR_t = (Σ_i RentPaid_{i,t}) / (Σ_i L2Fees_{i,t})`

The canonical definition lives in `docs/protocol.md`.

## Research goals

- measure STR over time
- decompose rent into components such as burn, tips, blob costs, and execution costs
- compare regimes before and after major protocol changes such as Dencun
- study counterfactual policy ideas, including blob-fee floor or reserve mechanisms

## Source priority

When sources disagree, the project prioritizes:

1. on-chain computed Ethereum L1 costs
2. growthepie exports for L2 fees and related triangulation series
3. L2BEAT cost series for sanity checks

On-chain rent computation is supported through BigQuery public Ethereum tables and an RPC fallback path.

## Repository structure

- `docs/`: research plans, runbooks, and the protocol lock
- `contracts/`: schemas, assumptions, data dictionary, and canonical modeling artifacts
- `registry/`: rollup universe definitions and attribution evidence
- `src/`: ETL, validation, and analysis code
- `data/`: local artifact layout and manifests
- `reports/`: generated research outputs
- `.orchestrator/`: task coordination files for the multi-agent workflow

## Reproducibility and gates

```bash
make gate
make test
```

These commands are the fastest way to check that the repo remains internally consistent after changes.

## Why this repo is distinctive

This project is not just "crypto analysis" in the abstract. It combines:

- metric design
- protocol-locked research definitions
- deterministic validation
- explicit source priority rules
- coordination discipline for larger empirical workflows

## Operational notes

The repo uses explicit tasks under `.orchestrator/` to support parallel work with clear ownership boundaries. For operating guidance, see:

- `docs/runbook_swarm.md`
- `docs/runbook_swarm_automation.md`
