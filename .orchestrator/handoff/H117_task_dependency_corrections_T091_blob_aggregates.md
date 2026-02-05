# Handoff H117 — Task dependency correction: T091 requires on-chain blob aggregates

## Summary (1–3 sentences)

Wired the cross-source reconciliation task (T091) to explicitly depend on L1 block-header extraction (T087B) so the planned “Blobscan vs on-chain blobGasUsed” sanity check has its required on-chain input available deterministically.

## What changed / what exists now

- Files/paths:
  - `.orchestrator/backlog/T091_validation_cross_source_reconciliation_suite.md`: added dependency on `T087B` and documented the additional input.
- Outputs produced:
  - No new datasets; task interface / sequencing metadata only.

## How to reproduce / verify

- Commands:
  - `make gate`
- Expected results:
  - `task_dependencies` passes; T091 lists `T087B` in its dependency set.

## Assumptions / risks

- Assumes the on-chain blobGasUsed aggregate used for validation is derived from the block header `blob_gas_used` field produced by T087B (preferred for total L1 aggregates).

## Open questions / next steps

- If T091 later uses rollup-attributed blob usage (not just total L1 blobGasUsed), consider also documenting reliance on T088’s decomposition outputs explicitly in the inputs section.

