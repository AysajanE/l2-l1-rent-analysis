# contracts/AGENTS.md — Contract Discipline

This directory contains canonical specs. Downstream work must not reinterpret them.

## MUST

- Only tasks in the Protocol/Contracts workstream may modify contracts.
- All contract changes require:
  - rationale
  - expected downstream impact
  - version bump if interfaces change
  - entry in `contracts/CHANGELOG.md`
- Prefer backward-compatible changes:
  - avoid renaming/removing fields without explicit migration approval
  - prefer additive optional fields where possible
- If a contract schema/template changes, update:
  - validators in `src/validation/`
  - relevant docs in `docs/`
  - examples/templates in `contracts/` that depend on it

## No implicit changes

If you need a new field/variable/assumption:
- update the contract first
- then update downstream code/tasks

## SHOULD

- Document the intent and units/semantics of required fields.
- Provide minimal passing examples for changed contracts where applicable.

## Stop condition

If a contract is ambiguous: block with @human and propose the smallest clarification.

## DO NOT

- Do not encode environment-specific paths or secrets in contracts.
