# `data/samples/l1/` — on-chain extraction acceptance tests (blob readiness)

Workstream W2 (on-chain) needs an explicit “blob readiness” check before any large backfill.
Providers can differ in whether they expose post‑Dencun (EIP‑4844) fields in tx payloads and
receipts; the swarm must fail fast if required fields are missing.

## Required environment

- Set an Ethereum mainnet JSON-RPC URL in `ETH_RPC_URL`.
  - Do not commit secrets.

## Probe (acceptance test)

Run the probe script (scans recent blocks by default):

```bash
export ETH_RPC_URL='https://...'
python src/etl/l1_probe_blob_ready.py --run-date YYYY-MM-DD
```

Expected behavior:

- Exit `0` when:
  - a type‑3 (blob) transaction is found, and
  - its receipt includes `blobGasUsed` and `blobGasPrice`, and
  - `burn_blob_wei = blobGasUsed * blobGasPrice` can be computed without extra calls.
- Exit `2` when the provider is reachable but required blob fields are missing.
- Exit `3` when `ETH_RPC_URL` is missing.

If no type‑3 tx is found in the default scan window, increase `--scan-blocks` or provide an
explicit range:

```bash
python src/etl/l1_probe_blob_ready.py --from-block 0 --to-block 0 --scan-blocks 20000
```

## Field expectations (aligned with `docs/protocol.md`)

For post‑Dencun blob fee computation, the extraction layer must support:

- Receipt fields (preferred):
  - `blobGasUsed` (quantity, per tx)
  - `blobGasPrice` (quantity, per tx; base fee per blob gas)
- Transaction fields (for diagnostics / blob counting fallback):
  - `type` (must identify `0x3`)
  - `blobVersionedHashes` (array; `blob_count = len(...)`)
  - `maxFeePerBlobGas` (optional)
- Block fields (for regime work / header-based fallback):
  - `blobGasUsed` (quantity, per block)
  - `excessBlobGas` (quantity, per block)

The probe script prints a JSON summary showing which fields are present and the derived
`burn_blob_wei` value.

