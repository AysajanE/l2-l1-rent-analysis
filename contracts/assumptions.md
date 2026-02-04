# Assumptions registry (contract)

This file records measurement/modeling assumptions that materially affect results.

Policy:
- Do not add assumptions silently in code or analysis.
- If a new assumption is required, propose it here and (if it is a scientific choice) block with `@human`.

## Assumptions

### A001 — EIP-7918 reserve-floor counterfactual is an applied floor on observed series

- Date added (UTC): 2026-02-04
- Owner: @human
- Applies to mode: empirical
- Description:
  - For the EIP-7918-style counterfactual, we do **not** simulate a new fee-market equilibrium.
  - We apply the reserve price as a deterministic floor to the observed blob base fee series:
    - `base_fee_per_blob_gas_cf_wei = max(base_fee_per_blob_gas_wei, reserve_blob_base_fee_wei)`
    - `reserve_blob_base_fee_wei = floor(BLOB_BASE_COST × base_fee_per_gas_wei / GAS_PER_BLOB)`
    - Constants: `BLOB_BASE_COST = 8192`, `GAS_PER_BLOB = 131072`.
- Rationale:
  - This produces an auditable “what would have been burned if a floor existed” series without requiring a full market-structure model.
- Expected impact:
  - Raises the lower tail of blob-fee burn in low-demand regimes; does not attempt to model behavioral responses or demand shifts.
- Evidence/links:
  - EIP-7918: Blob base fee bounded by execution cost.
  - EIP-4844: Shard Blob Transactions.
