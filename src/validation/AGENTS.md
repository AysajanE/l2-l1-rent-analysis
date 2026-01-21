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
