# registry/AGENTS.md — Attribution Registry Rules

The attribution registry is a measurement-critical artifact.

## Versioning

- Registry files are versioned: `rollup_registry_vX.csv` (or `.json`).
- Never delete entries; deprecate with `end_date` / `status` fields.

## Evidence required

Every address/label must include:
- evidence link (official docs/explorer/credible source)
- date verified
- notes on ambiguity (if any)

## Change log

Every registry change must update `registry/CHANGELOG.md` with:
- what changed
- why
- expected impact on attribution coverage
