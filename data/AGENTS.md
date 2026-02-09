# data/AGENTS.md — Data Handling Rules

## MUST

- Do not commit large data artifacts.
- Track schemas, manifests, and small samples only.
- Do not commit sensitive data (PII, secrets, credentials).
- Record provenance and license/access constraints for datasets (README or manifest).

## Append-only raw snapshots

- Raw snapshots are immutable and dated.
- Never overwrite; create a new dated snapshot.

## Provenance

Every raw snapshot must have a corresponding manifest entry:
- source name
- date fetched (UTC)
- command used
- file list + hashes (sha256)

## Golden samples

Small, tracked sample datasets live in `data/samples/` and are used for fast tests and gates.

## SHOULD

- Keep derived datasets under `data/processed/` with reproducible generation commands.
- Include checksums for important derived artifacts when feasible.

## DO NOT

- Do not mix raw and processed data in the same location.
- Do not create ad-hoc final files without a generation recipe.
