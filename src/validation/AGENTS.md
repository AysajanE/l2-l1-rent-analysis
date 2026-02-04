# src/validation/AGENTS.md — Validation Rules

Validation is the anti-dashboard-science layer.

## Requirements

- Implement deterministic checks that compare sources and flag deltas.
- Use tolerances from `docs/protocol.md`. Do not invent new ones.

## Outputs

- Machine-readable validation summary (JSON) under `reports/validation/`
- Human-readable report (MD) under `reports/validation/`

## Failure policy

If validation fails beyond tolerance, block with:
- where it fails
- plausible causes
- minimal next experiment to isolate cause

## CLI contract (swarm-safe)

Validation scripts must:

- be deterministic and offline (no network calls),
- write:
  - machine-readable JSON under `reports/validation/` and
  - a short Markdown report under `reports/validation/`,
- follow exit codes:
  - `0` = pass
  - `2` = fail (beyond tolerance)
  - `3` = missing required inputs (or schema mismatch)

### JSON schema (minimum)

Top-level keys:

- `ok` (bool)
- `inputs` (list)
- `metrics` (object)
- `failures` (list)

Do not emit machine-specific absolute paths in reports; prefer repo-relative paths.
