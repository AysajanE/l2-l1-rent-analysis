from __future__ import annotations

"""On-chain ETL: extract L1 transactions + receipts (incl. blob fields).

Default extraction is *narrow*: it only keeps transactions whose `from` address is in the
registry's `batcher_addresses_json` allowlist (in-scope rollups). This keeps volumes feasible
for unattended runs while remaining attribution-safe (from-address match only).

Raw snapshots are append-only under `data/raw/l1/<as-of>/txs_receipts/...`.
Processed outputs are rebuildable under `data/processed/l1/` (gitignored).
"""

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.etl.offchain.files import ensure_dir, write_text_append_only  # noqa: E402
from src.etl.rpc_client import (  # noqa: E402
    DEFAULT_RPC_ENV_VAR,
    RpcClient,
    get_rpc_url_from_env,
    hex_quantity_to_int,
    int_to_hex_quantity,
)


def _repo_root() -> Path:
    return REPO_ROOT


def _parse_date(value: str, *, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {label} date (expected YYYY-MM-DD): {value!r}") from exc


def _utc_midnight_timestamp(d: date) -> int:
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return int(dt.timestamp())


def _rpc_client(rpc_url: str | None) -> RpcClient:
    url = rpc_url or get_rpc_url_from_env(DEFAULT_RPC_ENV_VAR)
    return RpcClient(url=url, timeout_seconds=30, retries=3, backoff_seconds=1.0)


def _block_timestamp_utc(block: dict[str, Any]) -> int:
    ts = block.get("timestamp")
    if ts is None:
        raise SystemExit("Block missing timestamp")
    return hex_quantity_to_int(ts)


def _find_first_block_at_or_after_ts(client: RpcClient, *, target_ts: int, lo: int, hi: int) -> int:
    left = lo
    right = hi
    while left < right:
        mid = (left + right) // 2
        block = client.call("eth_getBlockByNumber", [int_to_hex_quantity(mid), False])
        if not isinstance(block, dict):
            raise SystemExit(f"Unexpected block response for {mid}")
        ts = _block_timestamp_utc(block)
        if ts < target_ts:
            left = mid + 1
        else:
            right = mid
    return left


@dataclass(frozen=True)
class BlockRange:
    start: int
    end: int


def _iter_ranges(*, start: int, end: int, chunk_size: int) -> list[BlockRange]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    ranges: list[BlockRange] = []
    cur = start
    while cur <= end:
        nxt = min(end, cur + chunk_size - 1)
        ranges.append(BlockRange(start=cur, end=nxt))
        cur = nxt + 1
    return ranges


def _write_jsonl_append_only(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [json.dumps(r, sort_keys=True) for r in rows]
    text = "\n".join(lines) + ("\n" if lines else "")
    write_text_append_only(path, text, encoding="utf-8")


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
        "l1_txs_receipts",
        str(rel_snapshot_dir),
        "--as-of",
        as_of.isoformat(),
        "--",
        *_render_command_tokens_for_manifest(root),
    ]
    subprocess.run(cmd, cwd=root, check=True)
    return root / "data" / "raw_manifest" / f"l1_txs_receipts_{as_of.isoformat()}.json"


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

    out_path = root / "data" / "processed_manifest" / f"l1_txs_receipts_{as_of.isoformat()}.json"
    try:
        cmd: list[str] = [
            sys.executable,
            str(helper),
            "l1_txs_receipts",
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


def _load_registry_sender_allowlist(path: Path) -> set[str]:
    if not path.exists():
        raise SystemExit(f"registry not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit("registry missing header row")
        required = {"rollup_id", "in_scope", "status", "batcher_addresses_json"}
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise SystemExit(f"registry missing required columns: {missing}")

        allow: set[str] = set()
        for row in reader:
            in_scope = (row.get("in_scope") or "").strip().lower() in {"true", "1", "yes", "y"}
            status = (row.get("status") or "").strip().lower()
            if not in_scope or status == "deprecated":
                continue
            payload = (row.get("batcher_addresses_json") or "").strip()
            if payload == "":
                continue
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            addresses = obj.get("addresses")
            if not isinstance(addresses, list):
                continue
            for a in addresses:
                if not isinstance(a, dict):
                    continue
                addr = a.get("address")
                if isinstance(addr, str) and addr.strip():
                    allow.add(addr.strip().lower())
        if not allow:
            raise SystemExit("registry sender allowlist is empty (batcher_addresses_json missing?)")
        return allow


def _tx_type_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16) if value.startswith("0x") else int(value)
        except ValueError:
            return None
    return None


def _safe_len(value: Any) -> int | None:
    return len(value) if isinstance(value, list) else None


def _txs_jsonl_paths(txs_dir: Path) -> list[Path]:
    return sorted([p for p in txs_dir.glob("txs_*.jsonl") if p.is_file()]) if txs_dir.exists() else []


def _receipts_jsonl_paths(receipts_dir: Path) -> list[Path]:
    return sorted([p for p in receipts_dir.glob("receipts_*.jsonl") if p.is_file()]) if receipts_dir.exists() else []


def _write_processed_txs_csv(*, txs_dir: Path, out_csv: Path) -> int:
    paths = _txs_jsonl_paths(txs_dir)
    if not paths:
        raise SystemExit(f"No raw tx snapshot files found under: {txs_dir}")

    ensure_dir(out_csv.parent)
    fieldnames = [
        "tx_hash",
        "block_number",
        "tx_index",
        "from_address",
        "to_address",
        "tx_type",
        "blobVersionedHashes_count",
        "max_fee_per_gas_wei",
        "max_priority_fee_per_gas_wei",
        "max_fee_per_blob_gas_wei",
    ]
    rows_written = 0
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for path in paths:
            with path.open("r", encoding="utf-8") as rf:
                for raw_line in rf:
                    if not raw_line.strip():
                        continue
                    tx = json.loads(raw_line)
                    if not isinstance(tx, dict):
                        continue
                    tx_hash = tx.get("hash")
                    if not isinstance(tx_hash, str):
                        continue
                    bn = hex_quantity_to_int(tx.get("blockNumber"))
                    idx = hex_quantity_to_int(tx.get("transactionIndex"))
                    tx_type = _tx_type_int(tx.get("type"))
                    blob_count = _safe_len(tx.get("blobVersionedHashes"))
                    row = {
                        "tx_hash": tx_hash,
                        "block_number": str(bn),
                        "tx_index": str(idx),
                        "from_address": str(tx.get("from") or "").lower(),
                        "to_address": str(tx.get("to") or "").lower() if tx.get("to") is not None else "",
                        "tx_type": str(tx_type) if tx_type is not None else "",
                        "blobVersionedHashes_count": str(blob_count) if blob_count is not None else "",
                        "max_fee_per_gas_wei": str(hex_quantity_to_int(tx.get("maxFeePerGas"))) if tx.get("maxFeePerGas") is not None else "",
                        "max_priority_fee_per_gas_wei": str(hex_quantity_to_int(tx.get("maxPriorityFeePerGas"))) if tx.get("maxPriorityFeePerGas") is not None else "",
                        "max_fee_per_blob_gas_wei": str(hex_quantity_to_int(tx.get("maxFeePerBlobGas"))) if tx.get("maxFeePerBlobGas") is not None else "",
                    }
                    w.writerow(row)
                    rows_written += 1
    return rows_written


def _write_processed_receipts_csv(*, receipts_dir: Path, out_csv: Path) -> int:
    paths = _receipts_jsonl_paths(receipts_dir)
    if not paths:
        raise SystemExit(f"No raw receipt snapshot files found under: {receipts_dir}")

    ensure_dir(out_csv.parent)
    fieldnames = [
        "tx_hash",
        "block_number",
        "tx_index",
        "from_address",
        "to_address",
        "tx_type",
        "status",
        "gas_used",
        "effective_gas_price_wei",
        "blobGasUsed",
        "blobGasPrice",
    ]
    rows_written = 0
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for path in paths:
            with path.open("r", encoding="utf-8") as rf:
                for raw_line in rf:
                    if not raw_line.strip():
                        continue
                    rcpt = json.loads(raw_line)
                    if not isinstance(rcpt, dict):
                        continue
                    tx_hash = rcpt.get("transactionHash")
                    if not isinstance(tx_hash, str):
                        continue
                    bn = hex_quantity_to_int(rcpt.get("blockNumber"))
                    idx = hex_quantity_to_int(rcpt.get("transactionIndex"))
                    tx_type = _tx_type_int(rcpt.get("type"))
                    row = {
                        "tx_hash": tx_hash,
                        "block_number": str(bn),
                        "tx_index": str(idx),
                        "from_address": str(rcpt.get("from") or "").lower(),
                        "to_address": str(rcpt.get("to") or "").lower() if rcpt.get("to") is not None else "",
                        "tx_type": str(tx_type) if tx_type is not None else "",
                        "status": str(hex_quantity_to_int(rcpt.get("status"))) if rcpt.get("status") is not None else "",
                        "gas_used": str(hex_quantity_to_int(rcpt.get("gasUsed"))) if rcpt.get("gasUsed") is not None else "",
                        "effective_gas_price_wei": str(hex_quantity_to_int(rcpt.get("effectiveGasPrice"))) if rcpt.get("effectiveGasPrice") is not None else "",
                        "blobGasUsed": str(hex_quantity_to_int(rcpt.get("blobGasUsed"))) if rcpt.get("blobGasUsed") is not None else "",
                        "blobGasPrice": str(hex_quantity_to_int(rcpt.get("blobGasPrice"))) if rcpt.get("blobGasPrice") is not None else "",
                    }
                    w.writerow(row)
                    rows_written += 1
    return rows_written


def run_extract(
    *,
    rpc_url: str | None,
    as_of: date,
    start_date: date | None,
    end_date: date | None,
    from_block: int | None,
    to_block: int | None,
    chunk_size: int,
    resume: bool,
    registry_path: Path,
    filter_from_registry: bool,
    out_txs_csv: Path,
    out_receipts_csv: Path,
    write_manifest: bool,
) -> int:
    try:
        client = _rpc_client(rpc_url)
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": "missing_rpc_url", "env_var": DEFAULT_RPC_ENV_VAR, "error": str(exc)}, indent=2))
        return 3

    latest_hex = client.call("eth_blockNumber", [])
    latest = hex_quantity_to_int(latest_hex)

    allow_senders: set[str] | None = None
    if filter_from_registry:
        allow_senders = _load_registry_sender_allowlist(registry_path)

    # Resolve block range.
    if from_block is not None or to_block is not None:
        if from_block is None or to_block is None:
            raise SystemExit("Provide both --from-block and --to-block (or neither).")
        start_block = int(from_block)
        end_block = int(to_block)
    else:
        if start_date is None or end_date is None:
            raise SystemExit("Provide --start-date and --end-date (or explicit --from-block/--to-block).")
        start_ts = _utc_midnight_timestamp(start_date)
        end_exclusive_ts = _utc_midnight_timestamp(end_date) + 24 * 3600
        start_block = _find_first_block_at_or_after_ts(client, target_ts=start_ts, lo=0, hi=latest)
        end_exclusive_block = _find_first_block_at_or_after_ts(client, target_ts=end_exclusive_ts, lo=start_block, hi=latest)
        end_block = max(start_block, end_exclusive_block - 1)

    raw_root = _repo_root() / "data" / "raw" / "l1" / as_of.isoformat() / "txs_receipts"
    txs_dir = raw_root / "txs"
    receipts_dir = raw_root / "receipts"
    ensure_dir(txs_dir)
    ensure_dir(receipts_dir)

    ranges = _iter_ranges(start=start_block, end=end_block, chunk_size=chunk_size)
    counts = {
        "chunks_total": len(ranges),
        "chunks_written": 0,
        "chunks_skipped": 0,
        "blocks_scanned": 0,
        "txs_selected": 0,
        "receipts_fetched": 0,
    }

    for r in ranges:
        txs_path = txs_dir / f"txs_{r.start}_{r.end}.jsonl"
        receipts_path = receipts_dir / f"receipts_{r.start}_{r.end}.jsonl"
        if txs_path.exists() or receipts_path.exists():
            if txs_path.exists() and receipts_path.exists() and resume:
                counts["chunks_skipped"] += 1
                continue
            raise SystemExit(f"Refusing to overwrite existing raw chunk(s): {txs_path} / {receipts_path}")

        tx_rows: list[dict[str, Any]] = []
        receipt_rows: list[dict[str, Any]] = []

        for bn in range(r.start, r.end + 1):
            block = client.call("eth_getBlockByNumber", [int_to_hex_quantity(bn), True])
            if not isinstance(block, dict):
                raise SystemExit(f"Unexpected block response for {bn}")
            txs = block.get("transactions")
            if not isinstance(txs, list):
                continue

            for tx in txs:
                if not isinstance(tx, dict):
                    continue
                sender = tx.get("from")
                if not isinstance(sender, str) or sender.strip() == "":
                    continue
                sender_lc = sender.strip().lower()
                if allow_senders is not None and sender_lc not in allow_senders:
                    continue

                tx_hash = tx.get("hash")
                if not isinstance(tx_hash, str) or tx_hash.strip() == "":
                    continue

                tx_rows.append(tx)
                counts["txs_selected"] += 1

                receipt = client.call("eth_getTransactionReceipt", [tx_hash])
                if not isinstance(receipt, dict):
                    raise SystemExit(f"Unexpected receipt response for tx {tx_hash}")
                receipt_rows.append(receipt)
                counts["receipts_fetched"] += 1

            counts["blocks_scanned"] += 1

        _write_jsonl_append_only(txs_path, tx_rows)
        _write_jsonl_append_only(receipts_path, receipt_rows)
        counts["chunks_written"] += 1

    tx_rows_written = _write_processed_txs_csv(txs_dir=txs_dir, out_csv=out_txs_csv)
    receipt_rows_written = _write_processed_receipts_csv(receipts_dir=receipts_dir, out_csv=out_receipts_csv)

    if write_manifest:
        raw_manifest = _write_raw_manifest(snapshot_dir=raw_root, as_of=as_of)
        meta = {
            "range": {"start_block": start_block, "end_block": end_block, "latest_block": latest},
            "raw_counts": counts,
            "processed_counts": {"tx_rows": tx_rows_written, "receipt_rows": receipt_rows_written},
            "filtering": {"filter_from_registry": filter_from_registry, "registry_path": str(registry_path.resolve().relative_to(_repo_root().resolve())) if filter_from_registry else None},
            "required_fields": {
                "txs": ["tx_hash", "block_number", "tx_index", "from_address", "tx_type"],
                "receipts": ["tx_hash", "block_number", "tx_index", "gas_used", "effective_gas_price_wei", "status"],
            },
        }
        _write_processed_manifest(as_of=as_of, inputs=[raw_manifest], outputs=[out_txs_csv, out_receipts_csv], meta=meta)

    print(
        json.dumps(
            {
                "ok": True,
                "as_of_utc_date": as_of.isoformat(),
                "raw_dir": str(raw_root),
                "out_txs_csv": str(out_txs_csv),
                "out_receipts_csv": str(out_receipts_csv),
                "counts": {**counts, "tx_rows_written": tx_rows_written, "receipt_rows_written": receipt_rows_written},
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="l1_extract_txs_receipts.py")
    p.add_argument("--rpc-url", default=None, help=f"Optional JSON-RPC URL (else use ${DEFAULT_RPC_ENV_VAR})")
    p.add_argument("--as-of", required=True, help="UTC as-of date for snapshot/manifests (YYYY-MM-DD)")
    p.add_argument("--start-date", default=None, help="UTC start date (YYYY-MM-DD) for extraction window")
    p.add_argument("--end-date", default=None, help="UTC end date (YYYY-MM-DD, inclusive) for extraction window")
    p.add_argument("--from-block", type=int, default=None, help="Optional start block (inclusive)")
    p.add_argument("--to-block", type=int, default=None, help="Optional end block (inclusive)")
    p.add_argument("--chunk-size", type=int, default=50, help="Blocks per raw snapshot chunk file (tx extraction is heavy)")
    p.add_argument("--resume", action="store_true", help="Skip existing raw chunks instead of erroring")
    p.add_argument("--registry", default="registry/rollup_registry_v1.csv", help="Rollup registry path (for sender allowlist)")
    p.add_argument("--no-filter-from-registry", action="store_true", help="Extract all txs (very large; not recommended)")
    p.add_argument("--out-txs-csv", default="data/processed/l1/l1_txs.csv")
    p.add_argument("--out-receipts-csv", default="data/processed/l1/l1_receipts.csv")
    p.add_argument("--write-manifest", action="store_true", help="Write raw + processed manifests (append-only)")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    as_of = _parse_date(str(args.as_of), label="as_of")
    start_date = _parse_date(str(args.start_date), label="start_date") if args.start_date else None
    end_date = _parse_date(str(args.end_date), label="end_date") if args.end_date else None

    registry = Path(args.registry)
    registry_abs = registry if registry.is_absolute() else (_repo_root() / registry)
    out_txs_csv = Path(args.out_txs_csv)
    out_receipts_csv = Path(args.out_receipts_csv)
    out_txs_csv_abs = out_txs_csv if out_txs_csv.is_absolute() else (_repo_root() / out_txs_csv)
    out_receipts_csv_abs = out_receipts_csv if out_receipts_csv.is_absolute() else (_repo_root() / out_receipts_csv)

    return run_extract(
        rpc_url=str(args.rpc_url) if args.rpc_url else None,
        as_of=as_of,
        start_date=start_date,
        end_date=end_date,
        from_block=args.from_block,
        to_block=args.to_block,
        chunk_size=int(args.chunk_size),
        resume=bool(args.resume),
        registry_path=registry_abs,
        filter_from_registry=(not bool(args.no_filter_from_registry)),
        out_txs_csv=out_txs_csv_abs,
        out_receipts_csv=out_receipts_csv_abs,
        write_manifest=bool(args.write_manifest),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
