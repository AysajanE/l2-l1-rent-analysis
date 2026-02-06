from __future__ import annotations

"""On-chain ETL: extract L1 block headers (incl. blob header fields).

Raw snapshots are append-only under `data/raw/l1/<as-of>/blocks/`.
Processed output is rebuildable under `data/processed/l1/` (gitignored).

This script is intentionally stdlib-only and uses JSON-RPC (`eth_getBlockByNumber`).
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


DENCUN_DATE_UTC = date(2024, 3, 13)  # per docs/protocol.md (locked)


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
    """Binary search for the first block with timestamp >= target_ts."""
    if target_ts < 0:
        raise ValueError("target_ts must be >= 0")

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


def _write_blocks_jsonl_append_only(path: Path, blocks: list[dict[str, Any]]) -> None:
    lines = [json.dumps(b, sort_keys=True) for b in blocks]
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
        "l1_blocks",
        str(rel_snapshot_dir),
        "--as-of",
        as_of.isoformat(),
        "--",
        *_render_command_tokens_for_manifest(root),
    ]
    subprocess.run(cmd, cwd=root, check=True)
    return root / "data" / "raw_manifest" / f"l1_blocks_{as_of.isoformat()}.json"


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

    out_path = root / "data" / "processed_manifest" / f"l1_blocks_{as_of.isoformat()}.json"
    try:
        cmd: list[str] = [
            sys.executable,
            str(helper),
            "l1_blocks",
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


def _blocks_jsonl_paths(blocks_dir: Path) -> list[Path]:
    if not blocks_dir.exists():
        return []
    return sorted([p for p in blocks_dir.glob("blocks_*.jsonl") if p.is_file()])


def _parse_hex_optional(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return hex_quantity_to_int(value)
    except Exception:
        return None


def _to_iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _to_date_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def write_processed_blocks_csv(*, blocks_dir: Path, out_csv: Path) -> dict[str, int]:
    paths = _blocks_jsonl_paths(blocks_dir)
    if not paths:
        raise SystemExit(f"No raw block snapshot files found under: {blocks_dir}")

    ensure_dir(out_csv.parent)
    fieldnames = [
        "block_number",
        "block_hash",
        "timestamp",
        "timestamp_utc",
        "date_utc",
        "base_fee_per_gas_wei",
        "gas_used",
        "gas_limit",
        "blob_gas_used",
        "excess_blob_gas",
    ]

    counts = {"blocks_parsed": 0, "blocks_post_dencun": 0, "blocks_missing_blob_fields_post_dencun": 0}

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()

        for path in paths:
            with path.open("r", encoding="utf-8") as rf:
                for raw_line in rf:
                    if not raw_line.strip():
                        continue
                    block = json.loads(raw_line)
                    if not isinstance(block, dict):
                        continue
                    bn_hex = block.get("number")
                    if bn_hex is None:
                        continue
                    bn = hex_quantity_to_int(bn_hex)
                    ts = _block_timestamp_utc(block)
                    date_str = _to_date_utc(ts)
                    is_post = _parse_date(date_str, label="date_utc") >= DENCUN_DATE_UTC
                    if is_post:
                        counts["blocks_post_dencun"] += 1
                        if block.get("excessBlobGas") is None or block.get("blobGasUsed") is None:
                            counts["blocks_missing_blob_fields_post_dencun"] += 1

                    row = {
                        "block_number": str(bn),
                        "block_hash": str(block.get("hash") or ""),
                        "timestamp": str(ts),
                        "timestamp_utc": _to_iso_utc(ts),
                        "date_utc": date_str,
                        "base_fee_per_gas_wei": str(_parse_hex_optional(block.get("baseFeePerGas")) or ""),
                        "gas_used": str(_parse_hex_optional(block.get("gasUsed")) or ""),
                        "gas_limit": str(_parse_hex_optional(block.get("gasLimit")) or ""),
                        "blob_gas_used": str(_parse_hex_optional(block.get("blobGasUsed")) or ""),
                        "excess_blob_gas": str(_parse_hex_optional(block.get("excessBlobGas")) or ""),
                    }
                    w.writerow(row)
                    counts["blocks_parsed"] += 1

    if counts["blocks_missing_blob_fields_post_dencun"] > 0:
        raise SystemExit(
            "Post-Dencun blocks are missing required blob header fields (provider not blob-ready?): "
            f"missing_count={counts['blocks_missing_blob_fields_post_dencun']}"
        )
    return counts


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
    out_csv: Path,
    write_manifest: bool,
) -> int:
    try:
        client = _rpc_client(rpc_url)
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": "missing_rpc_url", "env_var": DEFAULT_RPC_ENV_VAR, "error": str(exc)}, indent=2))
        return 3

    latest_hex = client.call("eth_blockNumber", [])
    latest = hex_quantity_to_int(latest_hex)

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
        # Compute the first block >= start_ts and the first block >= end_exclusive_ts.
        start_block = _find_first_block_at_or_after_ts(client, target_ts=start_ts, lo=0, hi=latest)
        end_exclusive_block = _find_first_block_at_or_after_ts(client, target_ts=end_exclusive_ts, lo=start_block, hi=latest)
        end_block = max(start_block, end_exclusive_block - 1)

    raw_blocks_dir = _repo_root() / "data" / "raw" / "l1" / as_of.isoformat() / "blocks"
    ensure_dir(raw_blocks_dir)

    ranges = _iter_ranges(start=start_block, end=end_block, chunk_size=chunk_size)
    counts = {"chunks_total": len(ranges), "chunks_written": 0, "chunks_skipped": 0, "blocks_fetched": 0}

    for r in ranges:
        out_path = raw_blocks_dir / f"blocks_{r.start}_{r.end}.jsonl"
        if out_path.exists():
            if resume:
                counts["chunks_skipped"] += 1
                continue
            raise SystemExit(f"Refusing to overwrite existing raw chunk: {out_path}")

        blocks: list[dict[str, Any]] = []
        for bn in range(r.start, r.end + 1):
            block = client.call("eth_getBlockByNumber", [int_to_hex_quantity(bn), False])
            if not isinstance(block, dict):
                raise SystemExit(f"Unexpected block response for {bn}")
            blocks.append(block)
            counts["blocks_fetched"] += 1
        _write_blocks_jsonl_append_only(out_path, blocks)
        counts["chunks_written"] += 1

    processed_counts = write_processed_blocks_csv(blocks_dir=raw_blocks_dir, out_csv=out_csv)

    if write_manifest:
        raw_manifest = _write_raw_manifest(snapshot_dir=raw_blocks_dir, as_of=as_of)
        meta = {
            "range": {"start_block": start_block, "end_block": end_block, "latest_block": latest},
            "raw_counts": counts,
            "processed_counts": processed_counts,
            "required_columns": [
                "block_number",
                "block_hash",
                "timestamp_utc",
                "base_fee_per_gas_wei",
                "gas_used",
                "blob_gas_used",
                "excess_blob_gas",
            ],
        }
        _write_processed_manifest(as_of=as_of, inputs=[raw_manifest], outputs=[out_csv], meta=meta)

    print(json.dumps({"ok": True, "as_of_utc_date": as_of.isoformat(), "raw_dir": str(raw_blocks_dir), "out_csv": str(out_csv), "counts": {**counts, **processed_counts}}, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="l1_extract_blocks.py")
    p.add_argument("--rpc-url", default=None, help=f"Optional JSON-RPC URL (else use ${DEFAULT_RPC_ENV_VAR})")
    p.add_argument("--as-of", required=True, help="UTC as-of date for snapshot/manifests (YYYY-MM-DD)")
    p.add_argument("--start-date", default=None, help="UTC start date (YYYY-MM-DD) for extraction window")
    p.add_argument("--end-date", default=None, help="UTC end date (YYYY-MM-DD, inclusive) for extraction window")
    p.add_argument("--from-block", type=int, default=None, help="Optional start block (inclusive)")
    p.add_argument("--to-block", type=int, default=None, help="Optional end block (inclusive)")
    p.add_argument("--chunk-size", type=int, default=500, help="Blocks per raw snapshot chunk file")
    p.add_argument("--resume", action="store_true", help="Skip existing raw chunks instead of erroring")
    p.add_argument("--out-csv", default="data/processed/l1/l1_blocks.csv", help="Processed CSV output path")
    p.add_argument("--write-manifest", action="store_true", help="Write raw + processed manifests (append-only)")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    as_of = _parse_date(str(args.as_of), label="as_of")
    start_date = _parse_date(str(args.start_date), label="start_date") if args.start_date else None
    end_date = _parse_date(str(args.end_date), label="end_date") if args.end_date else None
    out_csv = Path(args.out_csv)
    out_csv_abs = out_csv if out_csv.is_absolute() else (_repo_root() / out_csv)

    return run_extract(
        rpc_url=str(args.rpc_url) if args.rpc_url else None,
        as_of=as_of,
        start_date=start_date,
        end_date=end_date,
        from_block=args.from_block,
        to_block=args.to_block,
        chunk_size=int(args.chunk_size),
        resume=bool(args.resume),
        out_csv=out_csv_abs,
        write_manifest=bool(args.write_manifest),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
