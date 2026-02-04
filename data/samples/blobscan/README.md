# `data/samples/blobscan/` — Blobscan endpoint notes + schema placeholders

Blobscan is used as a **convenience** source for blob-market aggregates and cross-checks.
It is not required for authoritative on-chain computation, and the pipeline must remain viable
without it (fallback: compute from L1 blocks/txs directly).

## Discovery notes (2026-02-04)

- Docs are available at: `https://docs.blobscan.com/docs/api`
- API base is documented as `https://api.blobscan.com/`, but it may be unavailable at times.
  - In this environment on 2026-02-04, `https://api.blobscan.com/` returned HTTP 503.

## Auth and fallback policy

Some Blobscan endpoints may require JWT/auth (per their docs). ETL must:

- Prefer public endpoints first.
- If a required endpoint returns `401/403`:
  - check for an explicit env var (recommended: `BLOBSCAN_API_KEY` or `BLOBSCAN_JWT`),
  - if missing, **fail fast** and mark the task blocked (do not improvise).
- If the service is unavailable (e.g., 5xx) or no public endpoint exists:
  - block with `@human` and rely on on-chain-derived blob aggregates instead.

## Required fields for this project (schema target)

When Blobscan data is available, the normalized daily table (`blobscan_daily`) should include:

- `date_utc` (YYYY-MM-DD, UTC)
- `l1_blob_base_fee_wei` (integer; wei per blob gas) — integer-safe regime input
- `l1_blob_gas_used` (integer; blob gas)
- `blob_tx_count` (integer; count)

Optional helper fields:

- `blobs_count` (integer)
- `excess_blob_gas` (integer)

## Repro commands (expected once ETL exists)

```bash
python src/etl/blobscan_fetch.py --run-date YYYY-MM-DD
python scripts/make_raw_manifest.py blobscan data/raw/blobscan/YYYY-MM-DD --as-of YYYY-MM-DD -- \
  python src/etl/blobscan_fetch.py --run-date YYYY-MM-DD
```
