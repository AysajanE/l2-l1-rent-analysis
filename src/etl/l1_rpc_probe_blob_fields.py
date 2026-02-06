from __future__ import annotations

"""On-chain: RPC capability probe for blob fee fields (type-3 tx).

This is a fast acceptance test that the configured RPC endpoint can expose the minimal
fields required to compute blob fee burn (`burn_blob_wei`) for at least one post-Dencun
type-3 transaction.

Outputs (by default):
- Raw snapshots (append-only): `data/raw/l1/<as-of>/probe/...`
- Raw manifest (tracked): `data/raw_manifest/l1_probe_<as-of>.json` (when --write-manifest)
- Probe report (not committed): `data/processed/l1/l1_rpc_probe_blob_fields_report.json`
- Processed manifest (tracked): `data/processed_manifest/l1_probe_<as-of>.json` (when --write-manifest)
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.etl.eip4844 import GAS_PER_BLOB, base_fee_per_blob_gas_wei_from_excess_blob_gas  # noqa: E402
from src.etl.offchain.files import ensure_dir, write_text_append_only  # noqa: E402
from src.etl.rpc_client import (  # noqa: E402
    DEFAULT_RPC_ENV_VAR,
    RpcClient,
    get_rpc_url_from_env,
    hex_quantity_to_int,
    int_to_hex_quantity,
)


DEFAULT_REPORT_PATH = REPO_ROOT / "data" / "processed" / "l1" / "l1_rpc_probe_blob_fields_report.json"


def _repo_root() -> Path:
    return REPO_ROOT


def _parse_date(value: str, *, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {label} date (expected YYYY-MM-DD): {value!r}") from exc


def _rpc_client(rpc_url: str | None) -> RpcClient:
    url = rpc_url or get_rpc_url_from_env(DEFAULT_RPC_ENV_VAR)
    return RpcClient(url=url, timeout_seconds=30, retries=3, backoff_seconds=1.0)


def _find_first_blob_tx(
    client: RpcClient,
    *,
    from_block: int,
    to_block: int,
    max_blocks: int,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Scan blocks (descending) and return (block, tx) for the first type-3 tx found."""
    if to_block < from_block:
        raise ValueError("to_block must be >= from_block")

    scanned = 0
    for bn in range(to_block, from_block - 1, -1):
        scanned += 1
        if scanned > max_blocks:
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
            if tx_type == 3:
                return block, tx
    return None


def _safe_len(value: Any) -> int | None:
    return len(value) if isinstance(value, list) else None


def _write_raw_snapshot(*, raw_dir: Path, filename: str, obj: Any) -> None:
    ensure_dir(raw_dir)
    path = raw_dir / filename
    write_text_append_only(path, json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _render_command_tokens_for_manifest(root: Path) -> list[str]:
    argv0 = Path(sys.argv[0])
    try:
        script_token = str(argv0.resolve().relative_to(root.resolve()))
    except Exception:
        script_token = sys.argv[0]
    return ["python", script_token, *sys.argv[1:]]


def _write_raw_manifest(*, snapshot_dir: Path, as_of: date) -> Path:
    root = _repo_root()
    helper = root / "scripts" / "make_raw_manifest.py"
    if not helper.exists():
        raise SystemExit(f"missing helper script (expected): {helper}")

    rel_snapshot_dir = snapshot_dir.resolve().relative_to(root.resolve())
    cmd = [
        sys.executable,
        str(helper),
        "l1_probe",
        str(rel_snapshot_dir),
        "--as-of",
        as_of.isoformat(),
        "--",
        *_render_command_tokens_for_manifest(root),
    ]
    subprocess.run(cmd, cwd=root, check=True)
    return root / "data" / "raw_manifest" / f"l1_probe_{as_of.isoformat()}.json"


def _write_processed_manifest(
    *,
    as_of: date,
    inputs: list[Path],
    outputs: list[Path],
    meta: dict[str, object],
) -> Path:
    root = _repo_root()
    helper = root / "scripts" / "make_processed_manifest.py"
    if not helper.exists():
        raise SystemExit(f"missing helper script (expected): {helper}")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tf:
        json.dump(meta, tf, indent=2, sort_keys=True)
        tf.write("\n")
        meta_path = Path(tf.name)

    out_path = root / "data" / "processed_manifest" / f"l1_probe_{as_of.isoformat()}.json"
    try:
        cmd: list[str] = [
            sys.executable,
            str(helper),
            "l1_probe",
            "--as-of",
            as_of.isoformat(),
            "--inputs",
            *[str(p.resolve().relative_to(root.resolve())) for p in inputs],
            "--outputs",
            *[str(p.resolve().relative_to(root.resolve())) for p in outputs],
            "--meta-json",
            str(meta_path),
            "--out",
            str(out_path.resolve().relative_to(root.resolve())),
            "--",
            *_render_command_tokens_for_manifest(root),
        ]
        subprocess.run(cmd, cwd=root, check=True)
    finally:
        try:
            meta_path.unlink()
        except OSError:
            pass
    return out_path


def run_probe(
    *,
    rpc_url: str | None,
    as_of: date,
    from_block: int | None,
    to_block: int | None,
    scan_latest_blocks: int,
    scan_max_blocks: int,
    raw_dir: Path,
    out_report: Path,
    write_manifest: bool,
) -> int:
    try:
        client = _rpc_client(rpc_url)
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": "missing_rpc_url", "env_var": DEFAULT_RPC_ENV_VAR, "error": str(exc)}, indent=2))
        return 3

    latest_hex = client.call("eth_blockNumber", [])
    latest = hex_quantity_to_int(latest_hex)

    # Range selection (defaults: scan from latest backwards).
    if to_block is None:
        to_block = latest
    if from_block is None:
        from_block = max(0, to_block - max(1, int(scan_latest_blocks)))

    found = _find_first_blob_tx(client, from_block=from_block, to_block=to_block, max_blocks=scan_max_blocks)
    if found is None:
        report = {
            "ok": False,
            "reason": "no_type3_blob_tx_found",
            "as_of_utc_date": as_of.isoformat(),
            "range": {"from_block": from_block, "to_block": to_block, "scan_latest_blocks": scan_latest_blocks, "scan_max_blocks": scan_max_blocks, "latest_block": latest},
            "rpc": {"env_var": DEFAULT_RPC_ENV_VAR, "url_provided_via_arg": bool(rpc_url)},
        }
        ensure_dir(out_report.parent)
        out_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    block, tx = found
    tx_hash = tx.get("hash")
    if not isinstance(tx_hash, str) or tx_hash.strip() == "":
        raise SystemExit("Unexpected tx hash in block response")

    receipt = client.call("eth_getTransactionReceipt", [tx_hash])
    if not isinstance(receipt, dict):
        raise SystemExit("Unexpected receipt response shape")

    # Raw snapshots (append-only; reproducible).
    _write_raw_snapshot(raw_dir=raw_dir, filename=f"block_{block.get('number','unknown')}.json", obj=block)
    _write_raw_snapshot(raw_dir=raw_dir, filename=f"tx_{tx_hash}.json", obj=tx)
    _write_raw_snapshot(raw_dir=raw_dir, filename=f"receipt_{tx_hash}.json", obj=receipt)

    receipt_blob_gas_used = receipt.get("blobGasUsed")
    receipt_blob_gas_price = receipt.get("blobGasPrice")

    blob_versioned_hashes = tx.get("blobVersionedHashes")
    blob_count = _safe_len(blob_versioned_hashes)
    derived_blob_gas_used = blob_count * GAS_PER_BLOB if blob_count is not None else None

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

    if blob_gas_used is None and derived_blob_gas_used is not None:
        blob_gas_used = int(derived_blob_gas_used)
        blob_gas_used_source = "tx.blobVersionedHashes_count*GAS_PER_BLOB"

    header_excess_blob_gas = block.get("excessBlobGas")
    base_fee_per_blob_gas_wei_from_header: int | None = None
    if base_fee_per_blob_gas_wei is None and header_excess_blob_gas is not None:
        try:
            excess = hex_quantity_to_int(header_excess_blob_gas)
            base_fee_per_blob_gas_wei_from_header = base_fee_per_blob_gas_wei_from_excess_blob_gas(excess)
            base_fee_per_blob_gas_wei = base_fee_per_blob_gas_wei_from_header
            base_fee_per_blob_gas_source = "header.excessBlobGas->EIP4844.fake_exponential"
        except Exception:
            base_fee_per_blob_gas_wei_from_header = None

    burn_blob_wei: int | None = None
    if blob_gas_used is not None and base_fee_per_blob_gas_wei is not None:
        burn_blob_wei = int(blob_gas_used) * int(base_fee_per_blob_gas_wei)

    ok = burn_blob_wei is not None
    report: dict[str, object] = {
        "ok": ok,
        "as_of_utc_date": as_of.isoformat(),
        "rpc": {"env_var": DEFAULT_RPC_ENV_VAR, "url_provided_via_arg": bool(rpc_url)},
        "range": {"from_block": from_block, "to_block": to_block, "scan_latest_blocks": scan_latest_blocks, "scan_max_blocks": scan_max_blocks, "latest_block": latest},
        "block": {
            "number": block.get("number"),
            "hash": block.get("hash"),
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
            "type": receipt.get("type"),
            "status": receipt.get("status"),
            "gasUsed": receipt.get("gasUsed"),
            "effectiveGasPrice": receipt.get("effectiveGasPrice"),
            "blobGasUsed": receipt_blob_gas_used,
            "blobGasPrice": receipt_blob_gas_price,
        },
        "derived": {
            "gas_per_blob": GAS_PER_BLOB,
            "blob_count": blob_count,
            "derived_blob_gas_used_from_hashes": derived_blob_gas_used,
            "blob_gas_used": blob_gas_used,
            "blob_gas_used_source": blob_gas_used_source,
            "base_fee_per_blob_gas_wei": base_fee_per_blob_gas_wei,
            "base_fee_per_blob_gas_source": base_fee_per_blob_gas_source,
            "base_fee_per_blob_gas_wei_from_excessBlobGas": base_fee_per_blob_gas_wei_from_header,
            "burn_blob_wei": burn_blob_wei,
        },
        "acceptance": {"type3_tx_found": True, "can_compute_burn_blob_wei": ok},
    }

    ensure_dir(out_report.parent)
    out_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))

    if write_manifest:
        raw_manifest_path = _write_raw_manifest(snapshot_dir=raw_dir, as_of=as_of)
        processed_manifest_inputs = [raw_manifest_path]
        processed_manifest_outputs = [out_report]
        meta = {
            "ok": ok,
            "raw_snapshot_dir": str(raw_dir.resolve().relative_to(_repo_root().resolve())),
            "report_path": str(out_report.resolve().relative_to(_repo_root().resolve())),
            "acceptance": report.get("acceptance"),
            "derived": report.get("derived"),
        }
        _write_processed_manifest(as_of=as_of, inputs=processed_manifest_inputs, outputs=processed_manifest_outputs, meta=meta)

    return 0 if ok else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="l1_rpc_probe_blob_fields.py")
    p.add_argument("--rpc-url", default=None, help=f"Optional JSON-RPC URL (else use ${DEFAULT_RPC_ENV_VAR})")
    p.add_argument("--as-of", required=True, help="UTC as-of date (YYYY-MM-DD) for snapshot/manifests")
    p.add_argument("--from-block", type=int, default=None, help="Optional start block number (inclusive)")
    p.add_argument("--to-block", type=int, default=None, help="Optional end block number (inclusive)")
    p.add_argument("--scan-latest-blocks", type=int, default=2000, help="Default scan window when from/to not provided")
    p.add_argument("--scan-max-blocks", type=int, default=2000, help="Hard cap on scanned blocks")
    p.add_argument("--out", dest="out_report", default=str(DEFAULT_REPORT_PATH), help="Output path for the probe report JSON")
    p.add_argument("--write-manifest", action="store_true", help="Write raw + processed manifests (append-only)")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    as_of = _parse_date(str(args.as_of), label="as_of")

    raw_dir = _repo_root() / "data" / "raw" / "l1" / as_of.isoformat() / "probe"
    out_report = Path(args.out_report)
    out_report_abs = out_report if out_report.is_absolute() else (_repo_root() / out_report)

    return run_probe(
        rpc_url=str(args.rpc_url) if args.rpc_url else None,
        as_of=as_of,
        from_block=args.from_block,
        to_block=args.to_block,
        scan_latest_blocks=int(args.scan_latest_blocks),
        scan_max_blocks=int(args.scan_max_blocks),
        raw_dir=raw_dir,
        out_report=out_report_abs,
        write_manifest=bool(args.write_manifest),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

