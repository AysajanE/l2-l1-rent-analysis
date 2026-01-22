# `data/samples/` — golden samples (tracked)

This directory holds **small, tracked** sample datasets used for fast, deterministic tests.

Rules:
- Samples must be tiny (seconds to load).
- Samples must have schemas/contracts (prefer `contracts/schemas/`).
- Unit tests and gates should run on samples only.
- Full dataset builds belong in separate make targets (not `make gate`).
