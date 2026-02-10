from __future__ import annotations

"""On-chain ETL: extract L1 transactions + receipts (incl. blob fields).

Default extraction is *narrow*: it only keeps transactions whose `from` address is in the
registry's `batcher_addresses_json` allowlist (in-scope rollups). This keeps volumes feasible
for unattended runs while remaining attribution-safe (from-address match only).

Raw snapshots are append-only under `data/raw/l1/<as-of>/{txs,receipts}/...`.
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


GAS_PER_BLOB = 131072  # EIP-4844
SAMPLE_WINDOW_START_UTC = date(2024, 2, 20)
SAMPLE_WINDOW_END_UTC = date(2024, 4, 30)


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


def _parse_required_int(value: str, *, label: str, path: Path, row_idx: int) -> int:
    text = value.strip()
    if text == "":
        raise SystemExit(f"{path}: row {row_idx} missing required integer field: {label}")
    try:
        n = int(text)
    except ValueError as exc:
        raise SystemExit(f"{path}: row {row_idx} invalid integer for {label}: {value!r}") from exc
    if n < 0:
        raise SystemExit(f"{path}: row {row_idx} negative integer for {label}: {n}")
    return n


def _parse_optional_int(value: str, *, label: str, path: Path, row_idx: int) -> int | None:
    text = value.strip()
    if text == "":
        return None
    try:
        n = int(text)
    except ValueError as exc:
        raise SystemExit(f"{path}: row {row_idx} invalid integer for {label}: {value!r}") from exc
    if n < 0:
        raise SystemExit(f"{path}: row {row_idx} negative integer for {label}: {n}")
    return n


def _validate_required_columns(*, path: Path, fieldnames: list[str] | None, required: set[str]) -> None:
    if fieldnames is None:
        raise SystemExit(f"{path}: missing header row")
    missing = sorted(required - set(fieldnames))
    if missing:
        raise SystemExit(f"{path}: missing required columns: {missing}")


def _write_processed_txs_csv(*, txs_dir: Path, out_csv: Path) -> dict[str, int]:
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
    counts = {
        "rows_written": 0,
        "blob_tx_rows": 0,
        "blob_tx_rows_with_hashes": 0,
    }
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
                    if tx_type is None:
                        raise SystemExit(f"{path}: tx missing/invalid `type` for hash={tx_hash}")
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
                    if row["tx_hash"] == "" or row["block_number"] == "" or row["tx_index"] == "":
                        raise SystemExit(f"{path}: tx row missing required join keys for hash={tx_hash}")
                    w.writerow(row)
                    counts["rows_written"] += 1
                    if tx_type == 3:
                        counts["blob_tx_rows"] += 1
                        if blob_count is not None and blob_count > 0:
                            counts["blob_tx_rows_with_hashes"] += 1
    if counts["rows_written"] == 0:
        raise SystemExit(f"{out_csv}: no rows written after extraction/filtering")
    return counts


def _write_processed_receipts_csv(*, receipts_dir: Path, out_csv: Path) -> dict[str, int]:
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
    counts = {
        "rows_written": 0,
        "blob_receipt_rows": 0,
        "blob_receipt_rows_with_blob_fields": 0,
    }
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
                    if tx_type is None:
                        raise SystemExit(f"{path}: receipt missing/invalid `type` for tx={tx_hash}")
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
                    if row["gas_used"] == "" or row["effective_gas_price_wei"] == "" or row["status"] == "":
                        raise SystemExit(f"{path}: receipt missing required fee/status fields for tx={tx_hash}")
                    w.writerow(row)
                    counts["rows_written"] += 1
                    if tx_type == 3:
                        counts["blob_receipt_rows"] += 1
                        if row["blobGasUsed"] != "" and row["blobGasPrice"] != "":
                            counts["blob_receipt_rows_with_blob_fields"] += 1
    if counts["rows_written"] == 0:
        raise SystemExit(f"{out_csv}: no rows written after extraction/filtering")
    return counts


def _load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise SystemExit(f"Missing CSV file: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [dict(row) for row in reader]
        fieldnames = list(reader.fieldnames or [])
    return fieldnames, rows


def _assert_processed_schema(*, txs_path: Path, receipts_path: Path) -> dict[str, int]:
    tx_fields, tx_rows = _load_csv_rows(txs_path)
    receipt_fields, receipt_rows = _load_csv_rows(receipts_path)

    _validate_required_columns(
        path=txs_path,
        fieldnames=tx_fields,
        required={"tx_hash", "block_number", "tx_index", "tx_type", "blobVersionedHashes_count"},
    )
    _validate_required_columns(
        path=receipts_path,
        fieldnames=receipt_fields,
        required={"tx_hash", "block_number", "tx_index", "tx_type", "gas_used", "effective_gas_price_wei", "blobGasUsed", "blobGasPrice"},
    )

    tx_index: dict[str, tuple[int, int, int, int | None]] = {}
    tx_blob_rows = 0
    for i, row in enumerate(tx_rows, start=2):
        tx_hash = (row.get("tx_hash") or "").strip()
        if tx_hash == "":
            raise SystemExit(f"{txs_path}: row {i} missing tx_hash")
        block_number = _parse_required_int(row.get("block_number") or "", label="block_number", path=txs_path, row_idx=i)
        tx_index_num = _parse_required_int(row.get("tx_index") or "", label="tx_index", path=txs_path, row_idx=i)
        tx_type = _parse_required_int(row.get("tx_type") or "", label="tx_type", path=txs_path, row_idx=i)
        if tx_type == 3:
            tx_blob_rows += 1
        blob_count = _parse_optional_int(
            row.get("blobVersionedHashes_count") or "",
            label="blobVersionedHashes_count",
            path=txs_path,
            row_idx=i,
        )
        tx_index[tx_hash] = (block_number, tx_index_num, tx_type, blob_count)

    receipt_blob_rows = 0
    receipt_blob_rows_with_fields = 0
    joined_rows = 0
    for i, row in enumerate(receipt_rows, start=2):
        tx_hash = (row.get("tx_hash") or "").strip()
        if tx_hash == "":
            raise SystemExit(f"{receipts_path}: row {i} missing tx_hash")
        if tx_hash not in tx_index:
            raise SystemExit(f"{receipts_path}: row {i} tx_hash not present in tx table: {tx_hash}")
        block_number = _parse_required_int(
            row.get("block_number") or "",
            label="block_number",
            path=receipts_path,
            row_idx=i,
        )
        tx_index_num = _parse_required_int(row.get("tx_index") or "", label="tx_index", path=receipts_path, row_idx=i)
        tx_type = _parse_required_int(row.get("tx_type") or "", label="tx_type", path=receipts_path, row_idx=i)
        _parse_required_int(row.get("gas_used") or "", label="gas_used", path=receipts_path, row_idx=i)
        _parse_required_int(
            row.get("effective_gas_price_wei") or "",
            label="effective_gas_price_wei",
            path=receipts_path,
            row_idx=i,
        )
        tx_block_number, tx_index_value, tx_type_value, _ = tx_index[tx_hash]
        if block_number != tx_block_number or tx_index_num != tx_index_value:
            raise SystemExit(
                f"{receipts_path}: row {i} join key mismatch for tx_hash={tx_hash} "
                f"(tx table block/index={tx_block_number}/{tx_index_value}, receipt={block_number}/{tx_index_num})"
            )
        if tx_type != tx_type_value:
            raise SystemExit(
                f"{receipts_path}: row {i} tx_type mismatch for tx_hash={tx_hash} "
                f"(tx={tx_type_value}, receipt={tx_type})"
            )
        if tx_type == 3:
            receipt_blob_rows += 1
            blob_gas_used = _parse_optional_int(
                row.get("blobGasUsed") or "",
                label="blobGasUsed",
                path=receipts_path,
                row_idx=i,
            )
            blob_gas_price = _parse_optional_int(
                row.get("blobGasPrice") or "",
                label="blobGasPrice",
                path=receipts_path,
                row_idx=i,
            )
            if blob_gas_used is not None and blob_gas_price is not None:
                receipt_blob_rows_with_fields += 1
        joined_rows += 1

    if joined_rows == 0:
        raise SystemExit(f"{receipts_path}: no receipt rows available")
    return {
        "tx_rows": len(tx_rows),
        "receipt_rows": len(receipt_rows),
        "tx_blob_rows": tx_blob_rows,
        "receipt_blob_rows": receipt_blob_rows,
        "receipt_blob_rows_with_blob_fields": receipt_blob_rows_with_fields,
    }


def _write_sample_csv(
    *,
    txs_path: Path,
    receipts_path: Path,
    out_sample_csv: Path,
    max_rows: int,
) -> dict[str, int]:
    if max_rows <= 0:
        raise SystemExit("--sample-max-rows must be > 0")

    _, tx_rows = _load_csv_rows(txs_path)
    _, receipt_rows = _load_csv_rows(receipts_path)
    tx_by_hash: dict[str, dict[str, str]] = {}
    for row in tx_rows:
        tx_hash = (row.get("tx_hash") or "").strip()
        if tx_hash != "":
            tx_by_hash[tx_hash] = row

    joined: list[dict[str, str]] = []
    for row in receipt_rows:
        tx_hash = (row.get("tx_hash") or "").strip()
        tx = tx_by_hash.get(tx_hash)
        if tx is None:
            continue
        tx_type = (row.get("tx_type") or tx.get("tx_type") or "").strip()
        blob_gas_used = (row.get("blobGasUsed") or "").strip()
        blob_gas_price = (row.get("blobGasPrice") or "").strip()
        burn_blob_wei = ""
        can_compute_burn_blob_wei = "false"
        if blob_gas_used != "" and blob_gas_price != "":
            burn_blob_wei = str(int(blob_gas_used) * int(blob_gas_price))
            can_compute_burn_blob_wei = "true"
        elif tx_type == "3":
            blob_hashes_count = (tx.get("blobVersionedHashes_count") or "").strip()
            if blob_hashes_count != "" and blob_gas_price != "":
                derived_blob_gas_used = int(blob_hashes_count) * GAS_PER_BLOB
                burn_blob_wei = str(derived_blob_gas_used * int(blob_gas_price))
                can_compute_burn_blob_wei = "true"

        joined.append(
            {
                "tx_hash": tx_hash,
                "block_number": (row.get("block_number") or tx.get("block_number") or "").strip(),
                "tx_index": (row.get("tx_index") or tx.get("tx_index") or "").strip(),
                "tx_type": tx_type,
                "from_address": (tx.get("from_address") or row.get("from_address") or "").strip(),
                "to_address": (tx.get("to_address") or row.get("to_address") or "").strip(),
                "blobVersionedHashes_count": (tx.get("blobVersionedHashes_count") or "").strip(),
                "max_fee_per_blob_gas_wei": (tx.get("max_fee_per_blob_gas_wei") or "").strip(),
                "gas_used": (row.get("gas_used") or "").strip(),
                "effective_gas_price_wei": (row.get("effective_gas_price_wei") or "").strip(),
                "blobGasUsed": blob_gas_used,
                "blobGasPrice": blob_gas_price,
                "burn_blob_wei": burn_blob_wei,
                "can_compute_burn_blob_wei": can_compute_burn_blob_wei,
                "sample_window_start_utc": SAMPLE_WINDOW_START_UTC.isoformat(),
                "sample_window_end_utc": SAMPLE_WINDOW_END_UTC.isoformat(),
            }
        )

    def _sort_key(row: dict[str, str]) -> tuple[int, int]:
        return (int(row["block_number"]), int(row["tx_index"]))

    joined.sort(key=_sort_key)
    blob_rows = [r for r in joined if r["tx_type"] == "3"]
    non_blob_rows = [r for r in joined if r["tx_type"] != "3"]

    selected: list[dict[str, str]] = []
    if blob_rows:
        selected.extend(blob_rows[: min(5, max_rows)])
    remaining = max_rows - len(selected)
    if remaining > 0:
        selected.extend(non_blob_rows[:remaining])
    if not selected:
        raise SystemExit("No rows available to write sample CSV")

    blob_selected = [r for r in selected if r["tx_type"] == "3"]
    if not blob_selected:
        raise SystemExit(
            "No blob tx rows found in sample selection. "
            "Per task stop condition, block with @human if provider/range cannot surface type-3 rows."
        )
    if not any(r["can_compute_burn_blob_wei"] == "true" for r in blob_selected):
        raise SystemExit(
            "Blob tx rows found but none can deterministically compute burn_blob_wei from extracted fields "
            "(receipt preferred; fallback unavailable)."
        )

    ensure_dir(out_sample_csv.parent)
    fieldnames = [
        "tx_hash",
        "block_number",
        "tx_index",
        "tx_type",
        "from_address",
        "to_address",
        "blobVersionedHashes_count",
        "max_fee_per_blob_gas_wei",
        "gas_used",
        "effective_gas_price_wei",
        "blobGasUsed",
        "blobGasPrice",
        "burn_blob_wei",
        "can_compute_burn_blob_wei",
        "sample_window_start_utc",
        "sample_window_end_utc",
    ]
    with out_sample_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in selected:
            writer.writerow(row)

    return {
        "rows_joined": len(joined),
        "rows_selected": len(selected),
        "blob_rows_selected": len(blob_selected),
        "blob_rows_with_computable_burn_selected": sum(1 for r in blob_selected if r["can_compute_burn_blob_wei"] == "true"),
    }


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
    out_sample_csv: Path,
    sample_max_rows: int,
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

    raw_root = _repo_root() / "data" / "raw" / "l1" / as_of.isoformat()
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

    tx_summary = _write_processed_txs_csv(txs_dir=txs_dir, out_csv=out_txs_csv)
    receipt_summary = _write_processed_receipts_csv(receipts_dir=receipts_dir, out_csv=out_receipts_csv)
    schema_summary = _assert_processed_schema(txs_path=out_txs_csv, receipts_path=out_receipts_csv)
    sample_summary = _write_sample_csv(
        txs_path=out_txs_csv,
        receipts_path=out_receipts_csv,
        out_sample_csv=out_sample_csv,
        max_rows=sample_max_rows,
    )

    if write_manifest:
        raw_manifest = _write_raw_manifest(snapshot_dir=raw_root, as_of=as_of)
        meta = {
            "range": {"start_block": start_block, "end_block": end_block, "latest_block": latest},
            "raw_counts": counts,
            "processed_counts": {
                "tx_rows": tx_summary["rows_written"],
                "receipt_rows": receipt_summary["rows_written"],
                "tx_blob_rows": tx_summary["blob_tx_rows"],
                "receipt_blob_rows": receipt_summary["blob_receipt_rows"],
                "receipt_blob_rows_with_blob_fields": receipt_summary["blob_receipt_rows_with_blob_fields"],
            },
            "schema_assertions": {
                "required_join_keys": ["tx_hash", "block_number", "tx_index"],
                "required_tx_fields": ["tx_type", "blobVersionedHashes_count"],
                "required_receipt_fields": ["gas_used", "effective_gas_price_wei", "blobGasUsed", "blobGasPrice"],
                "validated_counts": schema_summary,
            },
            "sample": {
                "path": str(out_sample_csv.resolve().relative_to(_repo_root().resolve())),
                "window_start_utc": SAMPLE_WINDOW_START_UTC.isoformat(),
                "window_end_utc": SAMPLE_WINDOW_END_UTC.isoformat(),
                "max_rows": sample_max_rows,
                "counts": sample_summary,
            },
            "output_format": {
                "txs_path": str(out_txs_csv.resolve().relative_to(_repo_root().resolve())),
                "receipts_path": str(out_receipts_csv.resolve().relative_to(_repo_root().resolve())),
                "note": "CSV payload written to .parquet filename for stdlib-only portability (no parquet dependency).",
            },
            "filtering": {"filter_from_registry": filter_from_registry, "registry_path": str(registry_path.resolve().relative_to(_repo_root().resolve())) if filter_from_registry else None},
            "required_fields": {
                "txs": ["tx_hash", "block_number", "tx_index", "from_address", "tx_type", "blobVersionedHashes_count"],
                "receipts": ["tx_hash", "block_number", "tx_index", "gas_used", "effective_gas_price_wei", "status", "blobGasUsed", "blobGasPrice"],
            },
        }
        _write_processed_manifest(as_of=as_of, inputs=[raw_manifest], outputs=[out_txs_csv, out_receipts_csv, out_sample_csv], meta=meta)

    print(
        json.dumps(
            {
                "ok": True,
                "as_of_utc_date": as_of.isoformat(),
                "raw_dir": str(raw_root),
                "out_txs_csv": str(out_txs_csv),
                "out_receipts_csv": str(out_receipts_csv),
                "out_sample_csv": str(out_sample_csv),
                "counts": {
                    **counts,
                    **tx_summary,
                    **receipt_summary,
                    **schema_summary,
                    **sample_summary,
                },
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
    p.add_argument(
        "--out-txs-csv",
        default="data/processed/l1/l1_txs.parquet",
        help="Processed tx table path (CSV payload at .parquet path for stdlib portability)",
    )
    p.add_argument(
        "--out-receipts-csv",
        default="data/processed/l1/l1_receipts.parquet",
        help="Processed receipt table path (CSV payload at .parquet path for stdlib portability)",
    )
    p.add_argument("--out-sample-csv", default="data/samples/l1/l1_txs_receipts_sample.csv")
    p.add_argument("--sample-max-rows", type=int, default=40, help="Max rows in golden sample CSV")
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
    out_sample_csv = Path(args.out_sample_csv)
    out_txs_csv_abs = out_txs_csv if out_txs_csv.is_absolute() else (_repo_root() / out_txs_csv)
    out_receipts_csv_abs = out_receipts_csv if out_receipts_csv.is_absolute() else (_repo_root() / out_receipts_csv)
    out_sample_csv_abs = out_sample_csv if out_sample_csv.is_absolute() else (_repo_root() / out_sample_csv)

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
        out_sample_csv=out_sample_csv_abs,
        sample_max_rows=int(args.sample_max_rows),
        write_manifest=bool(args.write_manifest),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
