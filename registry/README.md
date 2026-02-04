# Registry

Measurement-critical registries (e.g., attribution mappings) live here.

Keep registries versioned and evidence-backed. See `registry/AGENTS.md`.

Current registries:
- `registry/rollup_registry_v1.csv` — rollup universe + evidence-backed attribution hooks.

## `rollup_registry_v1.csv` — column semantics

The registry is the source of truth for:

- `rollup_id` (the canonical join key used throughout the repo)
- mappings from vendor/source IDs → `rollup_id`
- attribution hooks (L1 addresses + evidence) for on-chain rent computation

### Rollup ID convention

- `rollup_id` is a stable, lowercase `snake_case` slug.
- For rollups present in growthepie, `rollup_id` **must equal** the growthepie chain key (`origin_key`).
  - Rationale: growthepie is the primary denominator source (`l2_fees_eth`), so aligning keys avoids ad-hoc joins.
- If a rollup is not present in growthepie, choose a stable `rollup_id` and leave `origin_key` blank with a note.

### Source key mappings

The following columns support deterministic joins:

- `origin_key`: growthepie chain key (from `https://api.growthepie.com/v1/master.json` → `chains`).
- `l2beat_slug`: L2BEAT project ID/slug (e.g., keys in `costs.table` response).
- `in_scope`: `true`/`false` — whether the rollup is included in STR computation per `docs/protocol.md`.

### Inclusion window + status

- `status`: `active` / `inactive` / `deprecated` (free text, but keep consistent).
- `start_date_utc` / `end_date_utc`: inclusion window boundaries (YYYY-MM-DD, UTC).
  - For bootstrap seeding, `start_date_utc` may be set to the analysis start date (`2022-01-01`) even if the rollup launched later;
    downstream joins should naturally begin when data becomes available.
  - If you know a more accurate launch/end date, update it with evidence and log it in `registry/CHANGELOG.md`.

## `batcher_addresses_json` schema (required before attribution)

On-chain attribution (W2/T088) requires a set of rollup-associated L1 addresses and evidence.
The `batcher_addresses_json` column stores a **versioned JSON object** per rollup row.

- Canonical schema: `registry/schemas/batcher_addresses_json_v1.schema.json`
- Field must be valid JSON when present; do not store arbitrary strings.

Recommended placeholder when unknown (seed stage):

```json
{"schema_version":1,"state":"unknown","addresses":[],"notes":"seeded; populate via T082"}
```

Address entries must include evidence and verification date (see `registry/AGENTS.md`).
