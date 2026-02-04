# Decision log (contract)

Chronological log of key project decisions (definitions, inclusions, tolerances, model choices).

Policy:
- If a decision affects results, record it here (with rationale and expected impact).

## Decisions

- 2026-01-23 — Lock STR schema + edge-case rules (owner: @human)
  - Decision:
    - STR panel schema is defined in `contracts/schemas/panel_schema_str_v1.yaml`.
    - Decomposition schema stub is defined in `contracts/schemas/panel_schema_decomp_v1.yaml`.
    - ETH is the canonical unit for fee/rent/profit series in contracts (`*_eth` fields are ETH, not wei).
    - Denominator-zero rule: if `Σ_i L2Fees_{i,t} == 0`, then `STR_t = NaN` (undefined).
    - Missingness rule: if either `L2Fees_{i,t}` or `RentPaid_{i,t}` is missing for a rollup-day, exclude that rollup-day from both numerator and denominator sums for ecosystem aggregates.
    - Canonical rollup key is `rollup_id` (registry-backed in `registry/rollup_registry_v1.csv`).
    - Vendor identity tolerance uses an explicit ETH-based formula (see `docs/protocol.md`).
    - Regime classification includes an explicit blob-fee floor regime definition (see `docs/protocol.md`).
  - Rationale:
    - Prevents “metric shopping” and schema drift by locking names/units/edge cases before ETL/metrics work scales.
  - Expected impact:
    - Downstream ETL/metrics/validation tasks can rely on stable field names and deterministic handling of zeros/missingness.
  - Links/refs:
    - `docs/protocol.md`
    - `contracts/data_dictionary.md`
    - `contracts/schemas/panel_schema_str_v1.yaml`
    - `contracts/schemas/panel_schema_decomp_v1.yaml`

- 2026-02-04 — Lock issuance definition, integer-safe blob fee regime inputs, EIP-7918 counterfactual parameters, and on-chain rollup cost schemas (owner: @human)
  - Decision:
    - Issuance:
      - `issuance_eth` is **gross** issuance to validators (consensus-layer issuance), **not net of burn**.
      - Primary source policy: `ultrasound.money` daily issuance series (snapshotted).
      - Secondary policy: a beacon-chain explorer / consensus feed for monthly tolerance checks.
    - Blob fee regime inputs:
      - Introduce `l1_blob_base_fee_wei` as the canonical integer-safe blob base fee input for regime classification.
      - Keep `l1_blob_base_fee_gwei` as presentation-only (do not compute regimes from floating gwei).
    - Blob burn computation (authoritative fields):
      - Preferred: receipt-provided `blobGasUsed` and `blobGasPrice` (wei) for blob txs.
      - Fallback: compute `base_fee_per_blob_gas_wei` deterministically from block header fields per EIP-4844.
    - EIP-7918 reserve/floor counterfactual (parameterization):
      - Constants: `BLOB_BASE_COST = 8192`, `GAS_PER_BLOB = 131072`.
      - Reserve floor: `reserve_blob_base_fee_wei = floor(BLOB_BASE_COST × base_fee_per_gas_wei / GAS_PER_BLOB)`.
      - Counterfactual blob base fee: `base_fee_per_blob_gas_cf_wei = max(base_fee_per_blob_gas_wei, reserve_blob_base_fee_wei)`.
      - “Floor binding” means `reserve_blob_base_fee_wei > base_fee_per_blob_gas_wei`.
    - Contracts added/extended:
      - Enriched panel contract: `contracts/schemas/panel_schema_str_v2.yaml` (table `daily_rollup_panel_v2`).
      - On-chain rollup cost contracts: `contracts/schemas/rollup_costs_daily_v1.yaml` and `contracts/schemas/rollup_costs_decomposition_daily_v1.yaml`.
      - Issuance contract: `contracts/schemas/issuance_daily_v1.yaml`.
      - Global decomposition contract extended with `l1_blob_base_fee_wei`: `contracts/schemas/panel_schema_decomp_v1.yaml`.
  - Rationale:
    - Removes scientific-definition drift (issuance/counterfactual) from downstream workstreams and prevents subtle blob-fee rounding errors from corrupting regime classification.
  - Expected impact:
    - W1 issuance ETL and W6 counterfactual analysis can implement deterministically against locked definitions.
    - W2 on-chain computation tasks have explicit schema contracts for rollup-attributed rent and decomposition outputs.
  - Links/refs:
    - `docs/protocol.md`
    - `contracts/data_dictionary.md`
    - `contracts/schemas/panel_schema_str_v2.yaml`
    - `contracts/schemas/rollup_costs_daily_v1.yaml`
    - `contracts/schemas/rollup_costs_decomposition_daily_v1.yaml`
    - `contracts/schemas/issuance_daily_v1.yaml`
