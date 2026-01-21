# scripts/AGENTS.md — Quality Gate Rules

Quality gates are the merge firewall.

## Design principles

- Gates must be **fast** (target: <30s locally).
- Gates must be **deterministic** (no web calls, no randomness).
- Prefer stdlib dependencies unless absolutely necessary.

## What gates should check (in order)

1) Repo invariants (required files exist)
2) Protocol completeness (no TODO stubs)
3) Workstreams completeness (ownership boundaries not blank)
4) Task hygiene (required sections, valid states)
5) Optional: unit tests / lint (only after `src/` exists)

## Output format

Each gate prints:
- ok flag
- details dict with actionable failures
