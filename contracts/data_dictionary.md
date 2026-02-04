# Data Dictionary (contract)

This file is the canonical reference for tables/fields/units/keys used in the project.

## Tables

### daily_rollup_panel

- Purpose: Analysis-ready daily rollup panel used to compute Settlement Take Rate (STR).
- Primary key: (`date_utc`, `rollup_id`)
- Grain: daily × rollup (UTC)
- Row inclusion rule: rows exist **iff** both `l2_fees_eth` and `rent_paid_eth` are present (missingness is represented by omitting the row, not by nulls).
- Source(s):
  - Primary denominator (`l2_fees_eth`): growthepie (ETH-native series)
  - Authoritative numerator (`rent_paid_eth`): on-chain computed rollup costs (see `rollup_costs_daily`)
  - Vendor series (`profit_eth`, `txcount`): growthepie (optional; used for sanity checks / controls)

#### Fields

| Field | Type | Units | Nullable | Description |
|---|---|---|---|---|
| `date_utc` | date | YYYY-MM-DD (UTC) | no | UTC date for daily aggregation |
| `rollup_id` | string | slug | no | Stable rollup identifier (see `registry/rollup_registry_v1.csv`) |
| `l2_fees_eth` | number | ETH | no | Total user fees paid on the rollup for `date_utc` (ETH-native) |
| `rent_paid_eth` | number | ETH | no | Total fees paid by the rollup to Ethereum L1 for settlement/DA/proofs for `date_utc` (ETH-native) |
| `profit_eth` | number | ETH | yes | Vendor-provided profit series; used only for sanity checks (`profit ≈ fees − rent`) |
| `txcount` | integer | count | yes | Transaction count (if provided) |

### daily_rollup_panel_v2

- Purpose: Enriched analysis-ready daily rollup panel (v2) for regime analysis, decomposition, and counterfactuals.
- Primary key: (`date_utc`, `rollup_id`)
- Grain: daily × rollup (UTC)
- Row inclusion rule: rows exist **iff** both `l2_fees_eth` and `rent_paid_eth` are present. Additional enrichment fields may be nullable.
- Source(s):
  - Core STR fields: same as `daily_rollup_panel` (on-chain `rent_paid_eth` + growthepie `l2_fees_eth`)
  - Decomposition fields: on-chain computed rollup decomposition (`rollup_costs_decomposition_daily`)
  - Regime variables: Blobscan and/or on-chain blocks aggregation (integer wei for blob base fee)
  - Macro inputs: price + issuance sources (see `issuance_daily`)

#### Fields (additive relative to v1)

| Field | Type | Units | Nullable | Description |
|---|---|---|---|---|
| `rent_base_fee_burn_eth` | number | ETH | yes | Rollup-attributed execution-layer base fee burn component of `rent_paid_eth` |
| `rent_blob_fee_burn_eth` | number | ETH | yes | Rollup-attributed blob fee burn component of `rent_paid_eth` |
| `rent_priority_fee_eth` | number | ETH | yes | Rollup-attributed execution-layer priority fee (tips) component of `rent_paid_eth` |
| `rent_blob_fee_burn_wei` | integer | wei | yes | Precision-safe integer version of `rent_blob_fee_burn_eth` |
| `rollup_blob_gas_used` | integer | blob gas | yes | Rollup-attributed blob gas used (used for counterfactual computations) |
| `l1_base_fee_per_gas_wei` | integer | wei per gas | no | Daily L1 base fee per gas level (required for EIP-7918 reserve-floor computations) |
| `l1_blob_base_fee_wei` | integer | wei per blob gas | yes | Daily blob base fee per blob gas level (integer-safe; used for regime classification) |
| `l1_blob_gas_used` | integer | blob gas | yes | Total L1 blob gas used (optional cross-check/regime field) |
| `eth_usd_close` | number | USD per ETH | yes | ETH/USD close price (secondary; interpretation only) |
| `issuance_eth` | number | ETH | yes | Gross ETH issuance to validators (consensus-layer issuance; not net of burn) |

### rollup_costs_daily

- Purpose: On-chain computed rollup-attributed daily L1 rent series (authoritative STR numerator input).
- Primary key: (`date_utc`, `rollup_id`)
- Grain: daily × rollup (UTC)
- Source(s): on-chain computed series (authoritative)

#### Fields

| Field | Type | Units | Nullable | Description |
|---|---|---|---|---|
| `date_utc` | date | YYYY-MM-DD (UTC) | no | UTC date for daily aggregation |
| `rollup_id` | string | slug | no | Stable rollup identifier (see `registry/rollup_registry_v1.csv`) |
| `rent_paid_eth` | number | ETH | no | Total L1 rent paid by the rollup for `date_utc` (ETH) |
| `rent_paid_wei` | integer | wei | yes | Precision-safe integer version of `rent_paid_eth` |

### rollup_costs_decomposition_daily

- Purpose: On-chain computed rollup-attributed daily L1 rent decomposition (burn vs tips; blob vs execution).
- Primary key: (`date_utc`, `rollup_id`)
- Grain: daily × rollup (UTC)
- Source(s): on-chain computed series (authoritative)

#### Fields

| Field | Type | Units | Nullable | Description |
|---|---|---|---|---|
| `date_utc` | date | YYYY-MM-DD (UTC) | no | UTC date for daily aggregation |
| `rollup_id` | string | slug | no | Stable rollup identifier (see `registry/rollup_registry_v1.csv`) |
| `rent_paid_eth` | number | ETH | no | Total rollup-attributed L1 rent paid on `date_utc` (ETH) |
| `rent_base_fee_burn_eth` | number | ETH | no | Execution-layer base fee burn component (ETH) |
| `rent_blob_fee_burn_eth` | number | ETH | no | Blob fee burn component (ETH) |
| `rent_priority_fee_eth` | number | ETH | no | Execution-layer priority fees (tips) component (ETH) |
| `rollup_blob_gas_used` | integer | blob gas | no | Total blob gas used by the rollup on `date_utc` (0 pre-Dencun or if no blobs used) |
| `unattributed_rent_eth` | number | ETH | yes | Residual bucket for unattributed rent due to incomplete registry coverage (optional) |
| `rent_paid_wei` | integer | wei | yes | Precision-safe integer version of `rent_paid_eth` |
| `rent_blob_fee_burn_wei` | integer | wei | yes | Precision-safe integer version of `rent_blob_fee_burn_eth` |
| `rent_base_fee_burn_wei` | integer | wei | yes | Precision-safe integer version of `rent_base_fee_burn_eth` |
| `rent_priority_fee_wei` | integer | wei | yes | Precision-safe integer version of `rent_priority_fee_eth` |

### issuance_daily

- Purpose: Daily ETH issuance series used for burn-share context.
- Primary key: (`date_utc`)
- Grain: daily (UTC)
- Definition: `issuance_eth` is **gross** issuance to validators (consensus-layer issuance), **not net of burn**.
- Source(s): primary `ultrasound.money` issuance series (snapshotted) with a secondary tolerance check where available.

#### Fields

| Field | Type | Units | Nullable | Description |
|---|---|---|---|---|
| `date_utc` | date | YYYY-MM-DD (UTC) | no | UTC date for daily aggregation |
| `issuance_eth` | number | ETH | no | Gross ETH issuance to validators on `date_utc` (not net of burn) |
| `source` | string | enum | no | Source identifier (primary: `ultrasound_money`; secondary allowed only for validation) |
| `method` | string | free text | yes | Short description of construction method |

### daily_l1_rent_decomposition

- Purpose: Daily Ethereum L1 rent components used for burn vs tips and blob vs calldata analysis.
- Primary key: (`date_utc`)
- Grain: daily (UTC)
- Source(s): on-chain computed series (authoritative)

#### Fields

| Field | Type | Units | Nullable | Description |
|---|---|---|---|---|
| `date_utc` | date | YYYY-MM-DD (UTC) | no | UTC date for daily aggregation |
| `l1_base_fee_burn_eth` | number | ETH | no | ETH burned via EIP-1559 base fee (execution layer) |
| `l1_blob_fee_burn_eth` | number | ETH | no | ETH burned via EIP-4844 blob base fee |
| `l1_priority_fee_eth` | number | ETH | no | ETH paid as priority fees (tips) |
| `l1_total_rent_eth` | number | ETH | no | Total L1 rent (burn + tips); must equal sum of components |
| `l1_blob_gas_used` | integer | blob gas | yes | Total blob gas used (optional cross-check field) |
| `l1_calldata_gas_used` | integer | gas | yes | Total calldata gas proxy (optional cross-check field) |
| `l1_blob_base_fee_wei` | integer | wei per blob gas | yes | Blob base fee per blob gas level (integer-safe; used for regime classification) |
| `l1_blob_base_fee_gwei` | number | gwei | yes | Blob base fee per blob gas level (presentation only; do not compute regimes from floating gwei) |

### <future_table_name>

- Purpose:
- Primary key:
- Grain:
- Source(s):

#### Fields

| Field | Type | Units | Nullable | Description |
|---|---|---|---|---|
|  |  |  |  |  |
