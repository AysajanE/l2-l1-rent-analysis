# scripts/AGENTS.md — Quality Gate Rules

Quality gates are the merge firewall.

## MUST

- Gates must be **fast** (target: <30s locally).
- Gates must be **deterministic** (no web calls, no randomness).
- Prefer stdlib dependencies unless absolutely necessary.
- Scripts must provide a CLI (`--help`) and be non-interactive by default.
- Scripts must fail fast with clear non-zero exit codes on failure.
- Avoid side effects at import time; use a `main()` entrypoint pattern.

## What gates should check (in order)

1) Repo invariants (required files exist)
2) Protocol completeness (no TODO stubs)
3) Workstreams completeness (ownership boundaries not blank)
4) Task hygiene (required sections, valid states)
5) Optional: unit tests / lint (only after `src/` exists)

## SHOULD

- Add `--dry-run` for destructive operations.
- Log key runtime parameters (inputs, outputs, date/window, seed where applicable).
- Keep scripts thin; place reusable logic in `src/`.

## Output format

Each gate prints:
- ok flag
- details dict with actionable failures

## DO NOT

- Do not hardcode absolute local paths.
- Do not silently swallow failures.
