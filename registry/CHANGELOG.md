# Registry changelog

All changes to registry artifacts must be recorded here.

Format:
- `YYYY-MM-DD` — what changed, why, and expected impact.

- 2026-01-23 — Added `registry/rollup_registry_v1.csv` header stub to lock the rollup identifier interface early and reduce ad-hoc ID drift.
- 2026-02-04 — Seeded a minimum viable rollup universe (13 in-scope rollups) and added deterministic source key mappings:
  - Added columns: `origin_key`, `l2beat_slug`, `in_scope`.
  - Seeded rows with `rollup_id` convention: `rollup_id == origin_key` for growthepie-covered rollups.
  - Documented and versioned the `batcher_addresses_json` schema (see `registry/schemas/batcher_addresses_json_v1.schema.json`).
  - Expected impact: unblocks W1 ETL joins and reduces rollup_id drift; on-chain address attribution coverage remains pending (T082).
- 2026-02-05 — Seeded `batcher_addresses_json.addresses` for the in-scope rollup set using L2BEAT’s on-chain-derived `discovered.json` outputs (commit `df691a0`):
  - Populated sender/operator allowlists (e.g., `batchPosters`, `batcherHash`, `operators`, `validators`, `sequencers`, `blockSubmitters`) as evidence-backed address entries.
  - Set per-address `evidence_url` to the pinned L2BEAT commit path and `verified_utc=2026-02-05`.
  - Expected impact: unblocks on-chain attribution (W2/T087→T088) without requiring manual address scraping as a first step; registry may still require periodic refresh if operator sets change.
