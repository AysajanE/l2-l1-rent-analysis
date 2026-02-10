# registry/AGENTS.md — Attribution Registry Rules

The attribution registry is a measurement-critical artifact.

## MUST

- Registry files are versioned: `rollup_registry_vX.csv` (or `.json`).
- Never delete entries; deprecate with `end_date` / `status` fields.
- Use stable identifiers and verification timestamps.
- Keep registry formats machine-readable and consistent.

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

## SHOULD

- Prefer append-only or versioned updates over in-place destructive mutation.
- Write updates atomically (tmp file then rename) when scripting registry writes.
- Link registry changes to relevant task ids/handoff notes.

## DO NOT

- Do not delete registry history unless explicitly authorized.
- Do not store large binary artifacts in `registry/`.
