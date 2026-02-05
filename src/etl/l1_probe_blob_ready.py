from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.etl.offchain.files import write_text_append_only  # noqa: E402
from src.etl.rpc_client import (  # noqa: E402
    DEFAULT_RPC_ENV_VAR,
    RpcClient,
    get_rpc_url_from_env,
    hex_quantity_to_int,
    int_to_hex_quantity,
)


GAS_PER_BLOB = 131072  # EIP-4844
MIN_BASE_FEE_PER_BLOB_GAS = 1  # EIP-4844
BLOB_BASE_FEE_UPDATE_FRACTION = 3338477  # EIP-4844


def _rpc_client(rpc_url: str | None) -> RpcClient:
    url = rpc_url or get_rpc_url_from_env(DEFAULT_RPC_ENV_VAR)
    return RpcClient(url=url, timeout_seconds=30, retries=3, backoff_seconds=1.0)


def _find_first_blob_tx(
    client: RpcClient,
    *,
    from_block: int,
    to_block: int,
    max_blocks: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Scan blocks (descending) and return (block, tx) for the first type-3 tx found."""
    if to_block < from_block:
        raise ValueError("to_block must be >= from_block")

    scanned = 0
    for bn in range(to_block, from_block - 1, -1):
        scanned += 1
        if max_blocks is not None and scanned > max_blocks:
            break

        block = client.call("eth_getBlockByNumber", [int_to_hex_quantity(bn), True])
        if not isinstance(block, dict):
            continue
        txs = block.get("transactions")
        if not isinstance(txs, list):
            continue
        for tx in txs:
            if not isinstance(tx, dict):
                continue
            typ = tx.get("type")
            tx_type: int | None = None
            if isinstance(typ, int):
                tx_type = typ
            elif isinstance(typ, str):
                try:
                    tx_type = int(typ, 16) if typ.startswith("0x") else int(typ)
                except ValueError:
                    tx_type = None
            if tx_type is None:
                continue
            if tx_type == 3:
                return block, tx
    return None


def _safe_len(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    return None


def _fake_exponential(*, factor: int, numerator: int, denominator: int) -> int:
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


def _base_fee_per_blob_gas_wei_from_excess_blob_gas(excess_blob_gas: int) -> int:
    if excess_blob_gas < 0:
        raise ValueError("excess_blob_gas must be >= 0")
    return _fake_exponential(
        factor=MIN_BASE_FEE_PER_BLOB_GAS,
        numerator=excess_blob_gas,
        denominator=BLOB_BASE_FEE_UPDATE_FRACTION,
    )


def cmd_probe(
    *,
    rpc_url: str | None,
    run_date: str | None,
    from_block: int | None,
    to_block: int | None,
    scan_blocks: int,
    out_path: str | None,
) -> int:
    try:
        client = _rpc_client(rpc_url)
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": "missing_rpc_url", "env_var": DEFAULT_RPC_ENV_VAR, "error": str(exc)}, indent=2))
        return 3

    latest_hex = client.call("eth_blockNumber", [])
    latest = hex_quantity_to_int(latest_hex)

    if to_block is None:
        to_block = latest
    if from_block is None:
        from_block = max(0, to_block - max(1, int(scan_blocks)))

    found = _find_first_blob_tx(client, from_block=from_block, to_block=to_block, max_blocks=scan_blocks)
    if found is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "no_type3_blob_tx_found",
                    "range": {"from_block": from_block, "to_block": to_block, "scan_blocks": scan_blocks, "latest_block": latest},
                    "notes": [
                        "Increase --scan-blocks or provide an explicit --from-block/--to-block range.",
                        "If the provider never returns type-3 txs, it may be missing post-Dencun fields.",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    block, tx = found
    tx_hash = tx.get("hash")
    if not isinstance(tx_hash, str):
        print(json.dumps({"ok": False, "reason": "missing_tx_hash_in_block"}, indent=2))
        return 2

    receipt = client.call("eth_getTransactionReceipt", [tx_hash])
    if not isinstance(receipt, dict):
        print(json.dumps({"ok": False, "reason": "unexpected_receipt_shape"}, indent=2))
        return 2

    receipt_blob_gas_used = receipt.get("blobGasUsed")
    receipt_blob_gas_price = receipt.get("blobGasPrice")
    receipt_ok = receipt_blob_gas_used is not None and receipt_blob_gas_price is not None

    blob_versioned_hashes = tx.get("blobVersionedHashes")
    blob_count = _safe_len(blob_versioned_hashes)
    derived_blob_gas_used = blob_count * GAS_PER_BLOB if blob_count is not None else None

    # Preferred: receipt fields (post-Dencun).
    blob_gas_used: int | None = None
    base_fee_per_blob_gas_wei: int | None = None
    blob_gas_used_source: str | None = None
    base_fee_per_blob_gas_source: str | None = None

    if receipt_blob_gas_used is not None:
        try:
            blob_gas_used = hex_quantity_to_int(receipt_blob_gas_used)
            blob_gas_used_source = "receipt.blobGasUsed"
        except Exception:
            blob_gas_used = None

    if receipt_blob_gas_price is not None:
        try:
            base_fee_per_blob_gas_wei = hex_quantity_to_int(receipt_blob_gas_price)
            base_fee_per_blob_gas_source = "receipt.blobGasPrice"
        except Exception:
            base_fee_per_blob_gas_wei = None

    # Fallbacks (EIP-4844): derive blob gas used from payload hashes, and base fee per blob gas from header excessBlobGas.
    if blob_gas_used is None and derived_blob_gas_used is not None:
        blob_gas_used = int(derived_blob_gas_used)
        blob_gas_used_source = "tx.blobVersionedHashes_count*GAS_PER_BLOB"

    header_excess_blob_gas = block.get("excessBlobGas")
    header_base_fee_per_blob_gas_wei: int | None = None
    if base_fee_per_blob_gas_wei is None and header_excess_blob_gas is not None:
        try:
            excess = hex_quantity_to_int(header_excess_blob_gas)
            header_base_fee_per_blob_gas_wei = _base_fee_per_blob_gas_wei_from_excess_blob_gas(excess)
            base_fee_per_blob_gas_wei = header_base_fee_per_blob_gas_wei
            base_fee_per_blob_gas_source = "header.excessBlobGas->EIP4844.fake_exponential"
        except Exception:
            header_base_fee_per_blob_gas_wei = None

    burn_blob_wei: int | None = None
    if blob_gas_used is not None and base_fee_per_blob_gas_wei is not None:
        burn_blob_wei = int(blob_gas_used) * int(base_fee_per_blob_gas_wei)

    out: dict[str, object] = {
        "ok": bool(receipt_ok and burn_blob_wei is not None),
        "rpc": {"env_var": DEFAULT_RPC_ENV_VAR, "url_provided_via_arg": bool(rpc_url)},
        "range": {"from_block": from_block, "to_block": to_block, "latest_block": latest, "scan_blocks": scan_blocks},
        "block": {
            "number": block.get("number"),
            "timestamp": block.get("timestamp"),
            "baseFeePerGas": block.get("baseFeePerGas"),
            "blobGasUsed": block.get("blobGasUsed"),
            "excessBlobGas": block.get("excessBlobGas"),
        },
        "tx": {
            "hash": tx_hash,
            "type": tx.get("type"),
            "blobVersionedHashes_count": blob_count,
            "maxFeePerBlobGas": tx.get("maxFeePerBlobGas"),
        },
        "receipt": {
            "blobGasUsed": receipt_blob_gas_used,
            "blobGasPrice": receipt_blob_gas_price,
            "effectiveGasPrice": receipt.get("effectiveGasPrice"),
            "gasUsed": receipt.get("gasUsed"),
            "status": receipt.get("status"),
        },
        "derived": {
            "derived_blob_gas_used_from_hashes": derived_blob_gas_used,
            "base_fee_per_blob_gas_wei_from_excessBlobGas": header_base_fee_per_blob_gas_wei,
            "blob_gas_used_source": blob_gas_used_source,
            "base_fee_per_blob_gas_source": base_fee_per_blob_gas_source,
            "burn_blob_wei": burn_blob_wei,
        },
        "acceptance": {
            "type3_tx_found": True,
            "receipt_has_blob_fields": bool(receipt_ok),
            "can_derive_blob_gas_used": bool(derived_blob_gas_used is not None),
            "can_derive_base_fee_per_blob_gas_wei": bool(header_base_fee_per_blob_gas_wei is not None),
            "can_compute_burn_blob_wei": bool(burn_blob_wei is not None),
        },
    }

    out["ok"] = bool(burn_blob_wei is not None)
    if not out["ok"]:
        out["reason"] = "missing_required_blob_fields"
        out["notes"] = [
            "Required for blob readiness: ability to compute burn_blob_wei for at least one type-3 tx using integer wei math.",
            "Preferred: receipt includes blobGasUsed and blobGasPrice. Fallbacks: blob gas from tx.blobVersionedHashes and base fee per blob gas from block excessBlobGas per EIP-4844.",
        ]

    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    print(text, end="")

    if out_path is not None or run_date is not None:
        out_dir = REPO_ROOT / "data" / "raw" / "l1" / (run_date or "probe")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = Path(out_path) if out_path else (out_dir / "rpc_probe_blob_ready.json")
        write_text_append_only(path, text, encoding="utf-8")

    return 0 if out["ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="l1_probe_blob_ready.py")
    p.add_argument("--rpc-url", default=None, help=f"Optional JSON-RPC URL (else use ${DEFAULT_RPC_ENV_VAR})")
    p.add_argument("--run-date", default=None, help="Optional UTC run date for raw snapshot folder naming (YYYY-MM-DD)")
    p.add_argument("--from-block", type=int, default=None, help="Optional start block number (inclusive)")
    p.add_argument("--to-block", type=int, default=None, help="Optional end block number (inclusive)")
    p.add_argument("--scan-blocks", type=int, default=2000, help="Max blocks to scan (descending) when searching for a type-3 tx")
    p.add_argument("--out", dest="out_path", default=None, help="Optional output path for writing probe JSON (append-only)")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return cmd_probe(
        rpc_url=str(args.rpc_url) if args.rpc_url else None,
        run_date=str(args.run_date) if args.run_date else None,
        from_block=args.from_block,
        to_block=args.to_block,
        scan_blocks=int(args.scan_blocks),
        out_path=str(args.out_path) if args.out_path else None,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
