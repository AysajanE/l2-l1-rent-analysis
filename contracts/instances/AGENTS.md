# contracts/instances/AGENTS.md — Instance Discipline

Instances are part of the contract surface for modeling projects.

## MUST

- Do not modify instances unless your task explicitly authorizes it.
- Version instance sets (e.g., `instance_set_v1/`) and treat them as immutable once used in results.
- Every instance set must have a manifest (inputs, hashes, generator command, timestamp).
- Include run-critical metadata when relevant:
  - contract id/version
  - parameterization
  - seed(s)
  - input dataset identifiers

## SHOULD

- Use consistent naming conventions including contract/instance set identifiers and timestamp where useful.
- Validate instances with repo validators before use.

## DO NOT

- Do not store generated results in `contracts/instances/` (store outputs under `reports/`).
- Do not store secrets or credentials in instances/manifests.
