# Handoff H087B — On-chain ETL extract L1 block headers + blob header fields

## Summary (1–3 sentences)
Completed T087B by hardening `src/etl/l1_extract_blocks.py` with explicit schema assertions, post-fork blob-header checks, and deterministic sample generation. Executed a tiny reproducible extraction around the Dencun fork boundary, produced append-only raw snapshots, and emitted tracked raw/processed manifests plus a committed sample. All required gates passed.

## What changed / what exists now

- Files/paths:
- `src/etl/l1_extract_blocks.py`
- `data/raw/l1/2026-02-10/blocks/blocks_19426580_19426620.jsonl` (append-only, untracked)
- `data/raw_manifest/l1_blocks_2026-02-10.json`
- `data/processed/l1/l1_blocks.parquet` (CSV payload to `.parquet` filename, untracked)
- `data/processed_manifest/l1_blocks_2026-02-10.json`
- `data/samples/l1/l1_blocks_sample.csv`
- `.orchestrator/backlog/T087B_onchain_etl_extract_l1_block_headers_blob_fields.md` (Status + Notes / Decisions only)

- Outputs produced:
- Processed table includes required columns: `block_number`, `block_hash`, `timestamp_utc`, `base_fee_per_gas_wei`, `gas_used`, `blob_gas_used`, `excess_blob_gas`
- Post-Dencun assertions use fork block boundary `19426587` (mainnet) for block-level correctness
- Sample is tiny/stable and spans pre/post fork with two rows (`19426586`, `19426587`) within canonical sample window

## How to reproduce / verify

- Commands:
- `make preflight-onchain`
- `python src/etl/l1_extract_blocks.py --as-of 2026-02-10 --from-block 19426580 --to-block 19426620 --chunk-size 64 --write-sample --write-manifest`
- `make gate`
- `make test`

- Expected results:
- Preflight returns `ok`
- Extractor writes raw snapshot and manifests:
  - `data/raw_manifest/l1_blocks_2026-02-10.json`
  - `data/processed_manifest/l1_blocks_2026-02-10.json`
- Extractor summary reports `blocks_fetched=41`, `blocks_post_dencun=34`, `blocks_missing_blob_fields_post_dencun=0`, `sample_rows=2`
- `make gate` passes
- `make test` passes (`Ran 42 tests ... OK`)

## Assumptions / risks

- `data/processed/l1/l1_blocks.parquet` currently stores CSV payload (portable stdlib path); downstream consumers should treat it accordingly unless parquet dependency is introduced later.
- Processed manifest `transform.git_sha` is `null` in this sandbox due unavailable git worktree metadata.

## Open questions / next steps

- T087C can reuse the same narrow around-fork extraction strategy for deterministic tiny samples when validating tx/receipt blob fields.
