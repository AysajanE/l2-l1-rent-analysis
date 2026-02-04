# Protocol Lock (Phase 0)

This file is the canonical definition set for this repo. If definitions conflict, stop and mark the relevant task `blocked` with `@human`.

## Research mode

- Mode: empirical

## Primary metric

- Name: Settlement Take Rate (STR)
- Formula: `STR_t = (Σ_i RentPaid_{i,t}) / (Σ_i L2Fees_{i,t})`
- Frequency: daily
- Units: Unitless ratio (0–1+); primary computation uses **ETH-native series** (USD series is secondary for interpretation only).

Definitions:
- `L2Fees_{i,t}`: total fees paid by users on rollup *i* on day *t*.
- `RentPaid_{i,t}`: total fees paid by rollup *i* to Ethereum L1 for settlement/DA/proofs on day *t*.
- Aggregation: the sum is over the **in-scope rollup universe** for day *t*.
- Denominator rule: if `Σ_i L2Fees_{i,t} == 0`, then `STR_t = NaN` (undefined; do not coerce to 0).
- Missingness rule (panel rows): if either `L2Fees_{i,t}` or `RentPaid_{i,t}` is missing for a rollup-day, exclude that rollup-day from both numerator and denominator sums for ecosystem-level aggregates.
- Panel construction rule: emit a `daily_rollup_panel` row **iff** both `l2_fees_eth` and `rent_paid_eth` are present (encode missingness via row omission, not nulls).

## Rollup inclusion criteria

In-scope rollups must:
- Be an L2 rollup (optimistic or ZK) that posts data to **Ethereum L1 mainnet**.
- Have a stable identifier in the project universe and be attributable in at least one primary data source.

Rollup universe representation:
- The canonical rollup identifier is `rollup_id` (see `registry/rollup_registry_v1.csv`).
- The universe may be time-varying (rollups may enter/exit); when a registry is present, prefer `start_date_utc` / `end_date_utc` + `status` to define active periods.

Out of scope:
- Non-Ethereum DA/settlement chains (may be discussed as competition, but excluded from STR computation).
- Sidechains that do not settle to Ethereum L1.

Time window:
- Start: 2022-01-01 (UTC)
- End: run date (UTC), daily frequency

## Data source priority

When sources disagree for the same concept, prefer (highest to lowest):
1. **On-chain computed** Ethereum L1 costs (authoritative for `RentPaid` and its decomposition).
2. **growthepie** exports (primary for `L2Fees`; secondary for vendor `rent_paid/profit` series).
3. **L2BEAT** costs series (triangulation / sanity check).

Rules:
- Prefer ETH-native series; convert to USD only using an explicit price series and document the source.
- Changing source priority requires a Workstream W0 task and explicit review.

## Auxiliary series (locked)

These definitions are required for decomposition/regime/counterfactual work. Downstream workstreams must not reinterpret them.

### Issuance (for burn-share context)

- Field name: `issuance_eth` (daily, UTC)
- Definition: **gross** ETH issuance to validators (consensus-layer issuance), **not net of burn**.
- Units: ETH (not wei).
- Source policy:
  - Primary: `ultrasound.money` daily issuance series (snapshotted; treated as an externally-derived dataset).
  - Secondary (tolerance check): a beacon-chain explorer / consensus feed.

### Blob fee computation (authoritative fields; integer-safe)

- Use **integer wei** for blob-fee inputs. Do not compute regimes using floating-point gwei.
- For a blob tx:
  - `blob_gas_used` must be available (receipt preferred).
  - `base_fee_per_blob_gas_wei` must be available either:
    - directly as `blobGasPrice` in the receipt (preferred), or
    - computed deterministically from block header fields per EIP-4844 (fallback).
  - Blob burn is computed as: `burn_blob_wei = blob_gas_used × base_fee_per_blob_gas_wei`.
- Execution-layer burn/tips use the standard EIP-1559 decomposition in wei:
  - `burn_base_wei = gas_used × base_fee_per_gas_wei` (block header)
  - `tips_wei = gas_used × (effective_gas_price_wei − base_fee_per_gas_wei)` (receipt + block header)

### EIP-7918 reserve/floor counterfactual (parameterization)

Counterfactual floor uses the EIP-7918 reserve-price definition (post-Dencun only):

- Constants:
  - `BLOB_BASE_COST = 8192` (EIP-7918)
  - `GAS_PER_BLOB = 131072` (EIP-4844)
- Reserve (floor) blob base fee per blob gas (wei):
  - `reserve_blob_base_fee_wei = floor(BLOB_BASE_COST × base_fee_per_gas_wei / GAS_PER_BLOB)`
- Counterfactual blob base fee per blob gas (wei):
  - `base_fee_per_blob_gas_cf_wei = max(base_fee_per_blob_gas_wei, reserve_blob_base_fee_wei)`
- “Floor binding” on a block/day means `reserve_blob_base_fee_wei > base_fee_per_blob_gas_wei`.

## Known regime dates

Daily regime boundaries are evaluated in **UTC**.

- Dencun / EIP-4844 activation on Ethereum mainnet: 2024-03-13 (UTC)
  - Treat dates `>= 2024-03-13` as **post-Dencun** for daily panels.
- Analysis start date: 2022-01-01 (UTC)

## Regime definitions (derived)

- Post-Dencun regime: `date_utc >= 2024-03-13` (UTC).
- Blob fee floor regime (post-Dencun only): identify contiguous runs of ≥7 days where:
  - `l1_blob_base_fee_wei <= floor(1.05 × min(l1_blob_base_fee_wei))`
  - Implementation (integer-safe): `l1_blob_base_fee_wei <= (min(l1_blob_base_fee_wei) * 105) // 100`

## Validation tolerances

Unless overridden by a task:

- Accounting identity (vendor series): `profit ≈ fees − rent_paid`
  - Tolerance (ETH): `abs(profit − (fees − rent_paid)) <= max(1e-9, 0.01 × max(abs(fees), abs(rent_paid), 1e-9))`
- Cross-source reconciliation (monthly aggregates, top rollups):
  - Target tolerance: 5–10%; otherwise explain and document the cause
- Blob usage cross-check (sample month):
  - `blobGasUsed` tolerance: ≤1% between Blobscan and on-chain daily aggregation
- Price inputs (monthly averages):
  - Tolerance: 1–2% between primary and secondary price sources
- Issuance inputs (monthly aggregates):
  - Target tolerance: 0.5–1% between primary and secondary issuance sources
