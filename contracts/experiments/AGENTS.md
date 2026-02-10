# contracts/experiments/AGENTS.md — Experiment Discipline

Experiments are part of the contract surface for modeling projects.

## MUST

- Experiments must be reproducible from declared inputs + seeds + environment info.
- Record experiment run manifests (timestamp, command, versions, output hashes).
- If experiment template semantics change, document:
  - what changed
  - what breaks
  - how to migrate

## SHOULD

- Keep templates minimal, composable, and machine-readable.
- Provide at least one canonical example per template.

## DO NOT

- Do not duplicate large schema blocks across templates when references/includes can avoid drift.
