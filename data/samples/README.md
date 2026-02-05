# `data/samples/` — golden samples (tracked)

This directory holds **small, tracked** sample datasets used for fast, deterministic tests.

Rules:
- Samples must be tiny (seconds to load).
- Samples must have schemas/contracts (prefer `contracts/schemas/`).
- Unit tests and gates should run on samples only.
- Full dataset builds belong in separate make targets (not `make gate`).

## Canonical sample window (for swarm + CI)

To keep cross-source sample-mode outputs comparable, the repo uses a single fixed sample window.

- Window (UTC, inclusive): `2024-02-20` → `2024-04-30`
  - Includes the Dencun boundary (`2024-03-13` UTC) and a full post‑Dencun month (`2024-04`).
- Canonical rollup subset for rollup-level sample panels (keep tiny):
  - `arbitrum`, `optimism`, `base`

Notes:
- For heavy on-chain extracts (txs/receipts), samples may be **sparse** within this window, but should include:
  - ≥1 pre‑Dencun day, ≥1 post‑Dencun day, and ≥1 day in April with a type‑3 tx when feasible.
- If a source cannot support this window (endpoint limits, provider gaps), document the exception in the source’s `data/samples/<source>/README.md` and block with `@human` if it impacts protocol-grade outputs.
