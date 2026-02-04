# Contracts changelog

All interface-relevant changes to canonical contracts must be recorded here.

Format:
- `YYYY-MM-DD` — what changed, why, and expected downstream impact.

Rules:
- If a change is interface-breaking, bump the contract version (e.g., `panel_schema_v2.yaml`) and add a migration note.

- 2026-01-22 — Added a minimal non-empty `contracts/schemas/panel_schema.yaml` stub so contract gates can prevent “comment-only” schemas.
- 2026-01-23 — Added versioned STR + decomposition schemas (`panel_schema_str_v1.yaml`, `panel_schema_decomp_v1.yaml`) and updated `contracts/data_dictionary.md` to lock field names/units early.
- 2026-02-04 — Added enriched panel contract `panel_schema_str_v2.yaml` and new on-chain/macro contracts (`rollup_costs_daily_v1.yaml`, `rollup_costs_decomposition_daily_v1.yaml`, `issuance_daily_v1.yaml`); extended decomposition schema and data dictionary with integer-safe `l1_blob_base_fee_wei` to prevent blob-fee rounding drift.
