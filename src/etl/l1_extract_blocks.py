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


# Mainnet Dencun activation block (EIP-4844). Used for block-level blob field assertions.
DENCUN_FORK_BLOCK_MAINNET = 19_426_587
CANONICAL_SAMPLE_WINDOW_START = date(2024, 2, 20)
CANONICAL_SAMPLE_WINDOW_END = date(2024, 4, 30)

PROCESSED_FIELDNAMES = [
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


def _require_hex_quantity(value: Any, *, field: str, block_number: int) -> int:
    if value in (None, ""):
        raise SystemExit(f"Block {block_number}: missing required field {field}")
    try:
        parsed = hex_quantity_to_int(value)
    except Exception as exc:
        raise SystemExit(f"Block {block_number}: invalid hex quantity for {field}: {value!r}") from exc
    if parsed < 0:
        raise SystemExit(f"Block {block_number}: negative value for {field}: {parsed}")
    return int(parsed)


def _require_non_empty_str(value: Any, *, field: str, block_number: int) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise SystemExit(f"Block {block_number}: missing/invalid required field {field}: {value!r}")
    return value


def _collect_processed_rows(*, blocks_dir: Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    paths = _blocks_jsonl_paths(blocks_dir)
    if not paths:
        raise SystemExit(f"No raw block snapshot files found under: {blocks_dir}")

    rows: list[dict[str, str]] = []
    counts = {
        "blocks_parsed": 0,
        "blocks_post_dencun": 0,
        "blocks_missing_blob_fields_post_dencun": 0,
    }

    for path in paths:
        with path.open("r", encoding="utf-8") as rf:
            for line_no, raw_line in enumerate(rf, start=1):
                if not raw_line.strip():
                    continue
                try:
                    block = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise SystemExit(f"{path}:{line_no}: invalid JSON in raw snapshot") from exc
                if not isinstance(block, dict):
                    raise SystemExit(f"{path}:{line_no}: expected object, got {type(block).__name__}")

                block_number_raw = block.get("number")
                if block_number_raw in (None, ""):
                    raise SystemExit(f"{path}:{line_no}: block missing required field number")
                try:
                    block_number = hex_quantity_to_int(block_number_raw)
                except Exception as exc:
                    raise SystemExit(f"{path}:{line_no}: invalid block number quantity: {block_number_raw!r}") from exc
                block_hash = _require_non_empty_str(block.get("hash"), field="hash", block_number=block_number)
                ts = _require_hex_quantity(block.get("timestamp"), field="timestamp", block_number=block_number)
                date_str = _to_date_utc(ts)
                timestamp_utc = _to_iso_utc(ts)

                base_fee_per_gas_wei = _require_hex_quantity(
                    block.get("baseFeePerGas"), field="baseFeePerGas", block_number=block_number
                )
                gas_used = _require_hex_quantity(block.get("gasUsed"), field="gasUsed", block_number=block_number)
                gas_limit = _require_hex_quantity(block.get("gasLimit"), field="gasLimit", block_number=block_number)

                blob_gas_used = _parse_hex_optional(block.get("blobGasUsed"))
                excess_blob_gas = _parse_hex_optional(block.get("excessBlobGas"))

                is_post_dencun = block_number >= DENCUN_FORK_BLOCK_MAINNET
                if is_post_dencun:
                    counts["blocks_post_dencun"] += 1
                    if blob_gas_used is None or excess_blob_gas is None:
                        counts["blocks_missing_blob_fields_post_dencun"] += 1
                        raise SystemExit(
                            "Post-Dencun block missing required blob header fields "
                            f"(provider not blob-ready?): block_number={block_number}"
                        )

                row = {
                    "block_number": str(block_number),
                    "block_hash": block_hash,
                    "timestamp": str(ts),
                    "timestamp_utc": timestamp_utc,
                    "date_utc": date_str,
                    "base_fee_per_gas_wei": str(base_fee_per_gas_wei),
                    "gas_used": str(gas_used),
                    "gas_limit": str(gas_limit),
                    "blob_gas_used": str(blob_gas_used) if blob_gas_used is not None else "",
                    "excess_blob_gas": str(excess_blob_gas) if excess_blob_gas is not None else "",
                }
                rows.append(row)
                counts["blocks_parsed"] += 1

    if counts["blocks_parsed"] == 0:
        raise SystemExit(f"Raw snapshot contains no parseable blocks under: {blocks_dir}")
    rows.sort(key=lambda r: int(r["block_number"]))
    return rows, counts


def _assert_processed_schema(rows: list[dict[str, str]]) -> None:
    required_columns = {
        "block_number",
        "block_hash",
        "timestamp_utc",
        "base_fee_per_gas_wei",
        "gas_used",
        "blob_gas_used",
        "excess_blob_gas",
    }
    for i, row in enumerate(rows):
        missing = sorted(required_columns - set(row.keys()))
        if missing:
            raise SystemExit(f"row {i}: missing required columns: {missing}")

        try:
            block_number = int(row["block_number"])
        except ValueError as exc:
            raise SystemExit(f"row {i}: invalid block_number: {row.get('block_number')!r}") from exc
        if block_number < 0:
            raise SystemExit(f"row {i}: negative block_number: {block_number}")

        if row.get("block_hash", "").strip() == "":
            raise SystemExit(f"row {i}: empty block_hash")

        for col in ["base_fee_per_gas_wei", "gas_used", "timestamp"]:
            try:
                value = int(str(row.get(col, "")))
            except ValueError as exc:
                raise SystemExit(f"row {i}: invalid integer value for {col}: {row.get(col)!r}") from exc
            if value < 0:
                raise SystemExit(f"row {i}: negative value for {col}: {value}")

        ts_utc = row.get("timestamp_utc", "")
        if not isinstance(ts_utc, str) or ts_utc.strip() == "":
            raise SystemExit(f"row {i}: missing timestamp_utc")
        try:
            datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SystemExit(f"row {i}: invalid timestamp_utc: {ts_utc!r}") from exc

        _parse_date(str(row.get("date_utc", "")), label="date_utc")

        if block_number >= DENCUN_FORK_BLOCK_MAINNET:
            for col in ["blob_gas_used", "excess_blob_gas"]:
                raw = row.get(col, "")
                if raw in ("", None):
                    raise SystemExit(f"row {i}: missing required post-Dencun field {col}")
                try:
                    value = int(str(raw))
                except ValueError as exc:
                    raise SystemExit(f"row {i}: invalid integer for {col}: {raw!r}") from exc
                if value < 0:
                    raise SystemExit(f"row {i}: negative value for {col}: {value}")


def _write_processed_table_csv_payload(*, out_path: Path, rows: list[dict[str, str]]) -> None:
    ensure_dir(out_path.parent)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PROCESSED_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in PROCESSED_FIELDNAMES})


def _build_sample_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, int | str]]:
    window_rows = [
        row
        for row in rows
        if CANONICAL_SAMPLE_WINDOW_START <= _parse_date(row["date_utc"], label="sample date_utc") <= CANONICAL_SAMPLE_WINDOW_END
    ]
    if not window_rows:
        raise SystemExit(
            "No blocks in canonical sample window "
            f"{CANONICAL_SAMPLE_WINDOW_START.isoformat()}..{CANONICAL_SAMPLE_WINDOW_END.isoformat()}"
        )

    pre_rows = [r for r in window_rows if int(r["block_number"]) < DENCUN_FORK_BLOCK_MAINNET]
    post_rows = [r for r in window_rows if int(r["block_number"]) >= DENCUN_FORK_BLOCK_MAINNET]
    if not pre_rows or not post_rows:
        raise SystemExit(
            "Sample requires both pre- and post-Dencun coverage; "
            f"pre_rows={len(pre_rows)} post_rows={len(post_rows)}"
        )

    # Keep sample tiny and deterministic: nearest pre-fork block + first post-fork block.
    pre_row = max(pre_rows, key=lambda r: int(r["block_number"]))
    post_row = min(post_rows, key=lambda r: int(r["block_number"]))

    sample_rows = [pre_row]
    if int(post_row["block_number"]) != int(pre_row["block_number"]):
        sample_rows.append(post_row)
    sample_rows.sort(key=lambda r: int(r["block_number"]))

    sample_meta: dict[str, int | str] = {
        "rows_in_window": len(window_rows),
        "rows_emitted": len(sample_rows),
        "sample_window_start": CANONICAL_SAMPLE_WINDOW_START.isoformat(),
        "sample_window_end": CANONICAL_SAMPLE_WINDOW_END.isoformat(),
    }
    return sample_rows, sample_meta


def _write_sample_csv(*, out_path: Path, rows: list[dict[str, str]]) -> None:
    ensure_dir(out_path.parent)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PROCESSED_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in PROCESSED_FIELDNAMES})


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
    out_processed: Path,
    write_sample: bool,
    sample_out: Path,
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

    rows, processed_counts = _collect_processed_rows(blocks_dir=raw_blocks_dir)
    _assert_processed_schema(rows)
    _write_processed_table_csv_payload(out_path=out_processed, rows=rows)

    sample_rows: list[dict[str, str]] = []
    sample_meta: dict[str, int | str] = {"rows_emitted": 0}
    if write_sample:
        sample_rows, sample_meta = _build_sample_rows(rows)
        _write_sample_csv(out_path=sample_out, rows=sample_rows)

    if write_manifest:
        raw_manifest = _write_raw_manifest(snapshot_dir=raw_blocks_dir, as_of=as_of)
        outputs = [out_processed]
        if write_sample:
            outputs.append(sample_out)
        meta = {
            "range": {"start_block": start_block, "end_block": end_block, "latest_block": latest},
            "raw_counts": counts,
            "processed_counts": processed_counts,
            "schema_assertions": {
                "required_columns": [
                    "block_number",
                    "block_hash",
                    "timestamp_utc",
                    "base_fee_per_gas_wei",
                    "gas_used",
                    "blob_gas_used",
                    "excess_blob_gas",
                ],
                "post_dencun_boundary_block_mainnet": DENCUN_FORK_BLOCK_MAINNET,
            },
            "sample": sample_meta,
            "output_format": {
                "path": str(out_processed.resolve().relative_to(_repo_root().resolve())),
                "note": "CSV payload written to .parquet filename for stdlib-only portability (no parquet dependency).",
            },
        }
        _write_processed_manifest(as_of=as_of, inputs=[raw_manifest], outputs=outputs, meta=meta)

    print(
        json.dumps(
            {
                "ok": True,
                "as_of_utc_date": as_of.isoformat(),
                "raw_dir": str(raw_blocks_dir),
                "out_processed": str(out_processed),
                "sample_out": str(sample_out) if write_sample else None,
                "counts": {
                    **counts,
                    **processed_counts,
                    "sample_rows": len(sample_rows),
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
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
    p.add_argument(
        "--out-processed",
        default="data/processed/l1/l1_blocks.parquet",
        help="Processed output path (CSV payload; .parquet extension recommended by task contract)",
    )
    p.add_argument("--out-csv", default=None, help="Deprecated alias for --out-processed")
    p.add_argument("--write-sample", action="store_true", help="Write deterministic canonical-window sample CSV")
    p.add_argument("--sample-out", default="data/samples/l1/l1_blocks_sample.csv", help="Sample CSV output path")
    p.add_argument("--write-manifest", action="store_true", help="Write raw + processed manifests (append-only)")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    as_of = _parse_date(str(args.as_of), label="as_of")
    start_date = _parse_date(str(args.start_date), label="start_date") if args.start_date else None
    end_date = _parse_date(str(args.end_date), label="end_date") if args.end_date else None
    out_processed_raw = str(args.out_csv) if args.out_csv else str(args.out_processed)
    out_processed = Path(out_processed_raw)
    out_processed_abs = out_processed if out_processed.is_absolute() else (_repo_root() / out_processed)
    sample_out = Path(str(args.sample_out))
    sample_out_abs = sample_out if sample_out.is_absolute() else (_repo_root() / sample_out)

    return run_extract(
        rpc_url=str(args.rpc_url) if args.rpc_url else None,
        as_of=as_of,
        start_date=start_date,
        end_date=end_date,
        from_block=args.from_block,
        to_block=args.to_block,
        chunk_size=int(args.chunk_size),
        resume=bool(args.resume),
        out_processed=out_processed_abs,
        write_sample=bool(args.write_sample),
        sample_out=sample_out_abs,
        write_manifest=bool(args.write_manifest),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
