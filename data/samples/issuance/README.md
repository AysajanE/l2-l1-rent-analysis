# `data/samples/issuance/` — issuance definition lock pointer + source notes

Issuance is used only for **burn-share context** (e.g., rollup-attributed burn vs issuance).

## Locked definition (W0)

Per `docs/protocol.md`:

- `issuance_eth` is **gross** ETH issuance to validators (consensus-layer issuance), **not net of burn**.

## Source notes (as of 2026-02-04)

The repo’s current W0 policy prefers ultrasound.money as a primary external series when feasible.
Public ultrasound.money endpoints observed:

- `https://ultrasound.money/api/v2/fees/gauge-rates`
  - includes `issuance_rate_yearly.eth` (a rate, not a daily issuance series)
- `https://ultrasound.money/api/v2/fees/supply-over-time`
  - supply over time (not gross issuance)

If a true daily gross issuance series is not directly available from ultrasound.money,
use a beacon-chain data source (e.g., beacon explorer API) and document:

- endpoint(s) + params
- method (epoch/slot aggregation → UTC day)
- tolerance checks vs a secondary source

## Required normalized fields (target schema)

- `date_utc` (YYYY-MM-DD, UTC)
- `issuance_eth` (ETH)
- `source` (string; primary should be stable)
- `method` (string; optional but recommended)

## Repro commands (expected once ETL exists)

```bash
python src/etl/issuance_fetch.py --run-date YYYY-MM-DD
python scripts/make_raw_manifest.py issuance data/raw/issuance/YYYY-MM-DD --as-of YYYY-MM-DD -- \
  python src/etl/issuance_fetch.py --run-date YYYY-MM-DD
```

## Canonical sample window

Golden samples should use the repo’s canonical sample window (see `data/samples/README.md`) so the enriched panel v2 sample can join deterministically.
