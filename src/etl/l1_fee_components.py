from __future__ import annotations

"""Fee-component helpers for on-chain rent computation (integer-safe).

Implements the protocol-locked decomposition in wei:
- execution burn: `burn_base_wei = gas_used * base_fee_per_gas_wei`
- execution tips: `tips_wei = gas_used * (effective_gas_price_wei - base_fee_per_gas_wei)`
- blob burn (type-3 only): `burn_blob_wei = blob_gas_used * base_fee_per_blob_gas_wei`

Blob base fee policy:
- Prefer receipt `blobGasPrice` when available.
- Fallback: compute base fee per blob gas deterministically from block header `excessBlobGas` per EIP-4844.
"""

from dataclasses import dataclass
from typing import Any

from src.etl.eip4844 import GAS_PER_BLOB, base_fee_per_blob_gas_wei_from_excess_blob_gas


@dataclass(frozen=True)
class FeeComponentsWei:
    burn_base_wei: int
    tips_wei: int
    burn_blob_wei: int
    blob_gas_used: int
    base_fee_per_blob_gas_wei: int | None
    blob_gas_used_source: str | None
    base_fee_per_blob_gas_source: str | None

    @property
    def rent_paid_wei(self) -> int:
        return int(self.burn_base_wei) + int(self.tips_wei) + int(self.burn_blob_wei)


def _tx_type_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16) if value.startswith("0x") else int(value)
        except ValueError:
            return None
    return None


def compute_fee_components_wei(
    *,
    gas_used: int,
    effective_gas_price_wei: int,
    base_fee_per_gas_wei: int,
    tx_type: int | str | None,
    # Blob fields (type-3):
    receipt_blob_gas_used: int | None,
    receipt_blob_gas_price_wei: int | None,
    tx_blob_versioned_hashes_count: int | None,
    block_excess_blob_gas: int | None,
    tx_max_fee_per_blob_gas_wei: int | None = None,
) -> FeeComponentsWei:
    if gas_used < 0:
        raise ValueError("gas_used must be >= 0")
    if effective_gas_price_wei < 0:
        raise ValueError("effective_gas_price_wei must be >= 0")
    if base_fee_per_gas_wei < 0:
        raise ValueError("base_fee_per_gas_wei must be >= 0")
    if effective_gas_price_wei < base_fee_per_gas_wei:
        raise ValueError("effective_gas_price_wei must be >= base_fee_per_gas_wei")

    burn_base_wei = int(gas_used) * int(base_fee_per_gas_wei)
    tips_wei = int(gas_used) * int(effective_gas_price_wei - base_fee_per_gas_wei)

    typ = _tx_type_int(tx_type)
    if typ != 3:
        return FeeComponentsWei(
            burn_base_wei=burn_base_wei,
            tips_wei=tips_wei,
            burn_blob_wei=0,
            blob_gas_used=0,
            base_fee_per_blob_gas_wei=None,
            blob_gas_used_source=None,
            base_fee_per_blob_gas_source=None,
        )

    blob_gas_used: int | None = None
    blob_gas_used_source: str | None = None
    if receipt_blob_gas_used is not None:
        blob_gas_used = int(receipt_blob_gas_used)
        blob_gas_used_source = "receipt.blobGasUsed"
    elif tx_blob_versioned_hashes_count is not None:
        if tx_blob_versioned_hashes_count < 0:
            raise ValueError("tx_blob_versioned_hashes_count must be >= 0")
        blob_gas_used = int(tx_blob_versioned_hashes_count) * GAS_PER_BLOB
        blob_gas_used_source = "tx.blobVersionedHashes_count*GAS_PER_BLOB"

    base_fee_per_blob_gas_wei: int | None = None
    base_fee_per_blob_gas_source: str | None = None
    if receipt_blob_gas_price_wei is not None:
        base_fee_per_blob_gas_wei = int(receipt_blob_gas_price_wei)
        base_fee_per_blob_gas_source = "receipt.blobGasPrice"
    elif block_excess_blob_gas is not None:
        if block_excess_blob_gas < 0:
            raise ValueError("block_excess_blob_gas must be >= 0")
        base_fee_per_blob_gas_wei = base_fee_per_blob_gas_wei_from_excess_blob_gas(int(block_excess_blob_gas))
        base_fee_per_blob_gas_source = "block.excessBlobGas->EIP4844.fake_exponential"

    if blob_gas_used is None:
        raise ValueError("missing blob gas used inputs for type-3 tx (need receipt_blob_gas_used or tx_blob_versioned_hashes_count)")
    if base_fee_per_blob_gas_wei is None:
        raise ValueError("missing blob base fee inputs for type-3 tx (need receipt_blob_gas_price_wei or block_excess_blob_gas)")
    if blob_gas_used < 0 or base_fee_per_blob_gas_wei < 0:
        raise ValueError("blob gas used and base fee per blob gas must be >= 0")

    if tx_max_fee_per_blob_gas_wei is not None and base_fee_per_blob_gas_wei > tx_max_fee_per_blob_gas_wei:
        raise ValueError(
            "header-derived base_fee_per_blob_gas_wei exceeds tx maxFeePerBlobGas; provider fields likely inconsistent"
        )

    burn_blob_wei = int(blob_gas_used) * int(base_fee_per_blob_gas_wei)
    return FeeComponentsWei(
        burn_base_wei=burn_base_wei,
        tips_wei=tips_wei,
        burn_blob_wei=burn_blob_wei,
        blob_gas_used=int(blob_gas_used),
        base_fee_per_blob_gas_wei=int(base_fee_per_blob_gas_wei),
        blob_gas_used_source=blob_gas_used_source,
        base_fee_per_blob_gas_source=base_fee_per_blob_gas_source,
    )

