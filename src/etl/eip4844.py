from __future__ import annotations

"""EIP-4844 helpers (integer-safe).

This module is intentionally stdlib-only and provides deterministic computation helpers
used across on-chain ETL and probes.
"""


GAS_PER_BLOB = 131072  # EIP-4844
MIN_BASE_FEE_PER_BLOB_GAS = 1  # EIP-4844
BLOB_BASE_FEE_UPDATE_FRACTION = 3338477  # EIP-4844


def fake_exponential(*, factor: int, numerator: int, denominator: int) -> int:
    """EIP-4844 fake_exponential (Taylor expansion approximation).

    Approximates: factor * e ** (numerator / denominator)
    Reference: https://eips.ethereum.org/EIPS/eip-4844
    """
    if factor < 0 or numerator < 0 or denominator <= 0:
        raise ValueError("invalid inputs")

    i = 1
    output = 0
    numerator_accum = factor * denominator
    while numerator_accum > 0:
        output += numerator_accum
        numerator_accum = (numerator_accum * numerator) // (denominator * i)
        i += 1
    return output // denominator


def base_fee_per_blob_gas_wei_from_excess_blob_gas(excess_blob_gas: int) -> int:
    if excess_blob_gas < 0:
        raise ValueError("excess_blob_gas must be >= 0")
    return fake_exponential(
        factor=MIN_BASE_FEE_PER_BLOB_GAS,
        numerator=excess_blob_gas,
        denominator=BLOB_BASE_FEE_UPDATE_FRACTION,
    )

