# src/AGENTS.md — Codebase Rules

`src/` contains all project code. Keep modules separated and reproducible.

## Module boundaries (MUST)

- `src/etl/`: data acquisition and transformation (network allowed)
- `src/validation/`: deterministic checks and reconciliation (no network)
- `src/analysis/`: analysis and figures (no network)
- `src/model/`: modeling/simulation/solvers (no invented assumptions; follow contracts)

## General standards (MUST)

- Prefer small, testable modules.
- No network calls outside `src/etl/`.
- Do not change contracts silently; update `contracts/` first if interfaces change.
- Separate IO from pure transformations where possible.
- Avoid side effects at import time.
- Add type hints for new/changed public functions.

## SHOULD

- Prefer `pathlib.Path` over raw string paths.
- Prefer focused config/dataclass objects over long argument lists.
- Add/update tests for behavior changes.

## DO NOT

- Do not add heavy dependencies without explicit task authorization.
- Do not hide failures; raise informative exceptions or return structured validation errors.
