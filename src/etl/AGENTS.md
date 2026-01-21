# src/etl/AGENTS.md — ETL Rules

ETL is allowed to touch the network. Everything must be reproducible.

## Non-negotiables

- Every external fetch must be cached/snapshotted.
- Never overwrite snapshots; write dated folders/files.
- Record endpoint, parameters, and timestamp in a small manifest file.

## Outputs

- Raw snapshots (append-only, not committed): `data/raw/<source>/<YYYY-MM-DD>/...`
- Normalized outputs (rebuildable, not committed): `data/processed/<source>/...`
- Provenance manifests (tracked): `data/raw_manifest/<source>_<YYYY-MM-DD>.json`

## Reliability

- Add retries with exponential backoff for APIs.
- Log failures with enough detail to replay.

## No hidden transforms

All transformation steps must be code, not manual edits.
