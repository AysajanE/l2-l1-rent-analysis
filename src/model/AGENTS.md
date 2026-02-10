# src/model/AGENTS.md — Modeling Rules

## MUST

- Implement exactly what is in `contracts/model_spec.*`.
- Do not invent missing assumptions; surface them and block if needed.
- Keep variants explicit (e.g., `model_v1`, `model_v2`) with clear differences.
- Make training/inference reproducible: fixed seeds, explicit params, deterministic settings where feasible.
- Keep model configuration explicit (config object/dataclass or equivalent).
- Version model artifacts and document reproduction steps.

## Outputs

- Must produce:
  - a callable solver/runner
  - a baseline run on benchmark instances
  - machine-readable results (JSON/CSV)
  - reproduction commands

## SHOULD

- Separate data prep, feature construction, training, and evaluation stages.
- Publish evaluation outputs (metrics and relevant plots/tables) under `reports/` with metadata.

## Validation

- Feasibility checks (constraints satisfied)
- Baseline replication (if defined)
- Sensitivity sanity checks (small perturbations behave as expected)

## DO NOT

- Do not hardcode environment-specific paths.
- Do not change default model behavior without updating tests/docs.
