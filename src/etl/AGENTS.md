# src/etl/AGENTS.md — ETL Rules

ETL is allowed to touch the network. Everything must be reproducible.

## MUST

- Every external fetch must be cached/snapshotted.
- Never overwrite snapshots; write dated folders/files.
- Record endpoint, parameters, and timestamp in a small manifest file.
- Preserve schema contracts; if schema changes are required, update validators/docs and document migration intent.
- Keep all transforms in code (no manual edits).

## Outputs

- Raw snapshots (append-only, not committed): `data/raw/<source>/<YYYY-MM-DD>/...`
- Normalized outputs (rebuildable, not committed): `data/processed/<source>/...`
- Provenance manifests (tracked): `data/raw_manifest/<source>_<YYYY-MM-DD>.json`

## SHOULD

- Add retries with exponential backoff for APIs.
- Log failures with enough detail to replay.
- Add parsing/transform tests for key schema/column guarantees.
- Cache expensive deterministic steps when useful.

## DO NOT

- Do not make hidden transforms outside code.
- Do not silently coerce schema-breaking inputs; fail with clear errors.
