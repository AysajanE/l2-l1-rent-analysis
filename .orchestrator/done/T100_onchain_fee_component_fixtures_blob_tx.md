---
task_id: T100
title: "On-chain: deterministic fixtures for fee-component math (incl. blob tx)"
workstream: W2
role: Worker
priority: medium
dependencies:
  - "T087B"
  - "T087C"
allowed_paths:
  - "src/etl/l1_fee_components.py"
  - "src/etl/l1_fee_components_selftest.py"
  - "data/samples/l1/fixtures/"
disallowed_paths:
  - "docs/protocol.md"
  - "contracts/"
  - "registry/"
  - "src/analysis/"
  - "src/validation/"
  - "data/raw/"
outputs:
  - "data/samples/l1/fixtures/blob_tx_fee_components_v1.json"
  - "src/etl/l1_fee_components_selftest.py"
gates:
  - "make gate"
stop_conditions:
  - "Missing required L1 sample inputs"
  - "Fee-component definitions require protocol reinterpretation"
---

# Task T100 — On-chain: deterministic fixtures for fee-component math (incl. blob tx)

## Context

Blob tx fee decomposition is easy to get subtly wrong (units, missing receipt fields, integer rounding).
Once `data/samples/l1/` exists (T087B/T087C), we need **small deterministic fixtures** to lock the fee-component math:

- execution burn: `burn_base_wei = gas_used × base_fee_per_gas_wei`
- execution tips: `tips_wei = gas_used × (effective_gas_price_wei − base_fee_per_gas_wei)`
- blob burn: `burn_blob_wei = blob_gas_used × base_fee_per_blob_gas_wei` (receipt preferred; fallback per protocol)

The goal is an offline, stable self-test that future refactors/providers can’t silently break.

## Inputs

- `docs/protocol.md` (read-only): integer-safe fee component definitions and blob field policy
- Committed samples (read-only; produced by T087B/T087C):
  - `data/samples/l1/l1_blocks_sample.csv`
  - `data/samples/l1/l1_txs_receipts_sample.csv`

## Outputs

- Fixture JSON(s) under `data/samples/l1/fixtures/` (tracked)
  - Must include at least one type‑3 (blob) tx case when feasible
  - Must store all numeric values as integers in wei/blob-gas units (no floats)
- Deterministic self-test runner:
  - `src/etl/l1_fee_components_selftest.py`
  - Reads fixtures and asserts computed components match expected values exactly.
  - Exit codes: `0` pass, `2` mismatch, `3` missing inputs.

## Success Criteria

- [ ] Fixtures include:
  - a blob tx case (`tx_type == 3`) with receipt blob fields when available
  - at least one non-blob tx case (type‑2) for EIP‑1559 burn/tips sanity
- [ ] Self-test produces exact matches using integer math only (no gwei floats)
- [ ] Running `python src/etl/l1_fee_components_selftest.py` exits `0` on pass
- [ ] `make gate` passes

## Status
- State: done
- Last updated: 2026-02-06
## Notes / Decisions

- 2026-02-05: Added per feedback “Medium-Priority Suggestions”: lock fee-component math via deterministic fixtures once L1 samples exist.



- 2026-02-06: Planner reconciliation — outputs already exist in repo; moved state to ready_for_review to clear control-plane drift before unattended fullscale preflight.


- 2026-02-06: Judge approval — promoted to done after repo-level gate/test/preflight checks and output existence verification to unblock downstream dependencies.
