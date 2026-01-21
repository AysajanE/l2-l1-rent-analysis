# data/AGENTS.md — Data Handling Rules

## Git policy

- Do not commit large data artifacts.
- Track schemas, manifests, and small samples only.

## Append-only raw snapshots

- Raw snapshots are immutable and dated.
- Never overwrite; create a new dated snapshot.

## Provenance

Every raw snapshot must have a corresponding manifest entry:
- source name
- date fetched (UTC)
- command used
- file list + hashes (sha256)
