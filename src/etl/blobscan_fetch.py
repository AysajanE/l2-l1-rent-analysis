from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
import urllib.error
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.etl.offchain.files import ensure_dir, write_text_append_only  # noqa: E402
from src.etl.offchain.http import http_get, http_get_text  # noqa: E402


BLOBSCAN_DOCS_URL = "https://docs.blobscan.com/docs/api"
BLOBSCAN_API_BASE_URL = "https://api.blobscan.com/"
BLOBSCAN_STATS_TIMESERIES_URL = f"{BLOBSCAN_API_BASE_URL}stats/timeseries"
BLOBSCAN_STATS_OVERALL_URL = f"{BLOBSCAN_API_BASE_URL}stats/overall"

TIMESERIES_METRICS = (
    "avgBlobGasPrice",
    "totalBlobGasUsed",
    "totalTransactions",
    "totalBlobs",
)

REQUIRED_COLUMNS = (
    "date_utc",
    "l1_blob_base_fee_wei",
    "l1_blob_gas_used",
)

SAMPLE_WINDOW_START = date(2024, 2, 20)
SAMPLE_WINDOW_END = date(2024, 4, 30)

PROCESSED_OUT_PATH = REPO_ROOT / "data" / "processed" / "blobscan" / "blobscan_daily.parquet"
SAMPLE_OUT_PATH = REPO_ROOT / "data" / "samples" / "blobscan" / "blobscan_daily_sample.csv"


def _parse_date(value: str, *, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {label} date (expected YYYY-MM-DD): {value!r}") from exc


def _as_utc_date_from_ts(ts: str) -> date:
    text = ts.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SystemExit(f"Invalid timestamp in Blobscan payload: {ts!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _parse_decimal(value: Any, *, label: str, date_utc: str) -> Decimal:
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, float):
        out = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip()
        if text == "":
            raise SystemExit(f"{label} is empty at date_utc={date_utc}")
        try:
            out = Decimal(text)
        except InvalidOperation as exc:
            raise SystemExit(f"{label} is not numeric at date_utc={date_utc}: {value!r}") from exc
    else:
        raise SystemExit(f"{label} has unsupported type at date_utc={date_utc}: {type(value).__name__}")

    if not out.is_finite():
        raise SystemExit(f"{label} must be finite at date_utc={date_utc}: {value!r}")
    return out


def _parse_int(value: Any, *, label: str, date_utc: str) -> int:
    if isinstance(value, bool):
        raise SystemExit(f"{label} must be integer-like at date_utc={date_utc}, got bool")

    if isinstance(value, int):
        out = value
    elif isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise SystemExit(f"{label} must be integer-like at date_utc={date_utc}, got {value!r}")
        out = int(value)
    elif isinstance(value, float):
        if not value.is_integer():
            raise SystemExit(f"{label} must be integer-like at date_utc={date_utc}, got {value!r}")
        out = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if text == "":
            raise SystemExit(f"{label} is empty at date_utc={date_utc}")
        try:
            out = int(text, 10)
        except ValueError as exc:
            raise SystemExit(f"{label} is not integer-like at date_utc={date_utc}: {value!r}") from exc
    else:
        raise SystemExit(f"{label} has unsupported type at date_utc={date_utc}: {type(value).__name__}")

    if out < 0:
        raise SystemExit(f"{label} must be >= 0 at date_utc={date_utc}, got {out}")
    return out


def _decimal_to_compact_string(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _safe_http_get_text(url: str, *, timeout_seconds: int = 90) -> str:
    try:
        return http_get_text(url, timeout_seconds=timeout_seconds, retries=3)
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
        if code in {401, 403}:
            raise SystemExit(
                "Blobscan endpoint requires authorization (HTTP "
                f"{code}) and no public fallback was configured. Block with @human."
            ) from exc
        if 500 <= code < 600:
            raise SystemExit(
                f"Blobscan endpoint unavailable (HTTP {code}). Source instability; block with @human."
            ) from exc
        raise SystemExit(f"Blobscan request failed with HTTP {code}: {exc.reason}") from exc
    except Exception as exc:
        raise SystemExit(f"Blobscan request failed: {exc}") from exc


def _render_command_tokens_for_manifest(root: Path) -> list[str]:
    argv0 = Path(sys.argv[0])
    try:
        script_token = str(argv0.resolve().relative_to(root.resolve()))
    except Exception:
        script_token = sys.argv[0]
    return ["python", script_token, *sys.argv[1:]]


def _write_raw_manifest(*, source: str, snapshot_dir: Path, as_of: date) -> Path:
    root = REPO_ROOT
    helper = root / "scripts" / "make_raw_manifest.py"
    if not helper.exists():
        raise SystemExit(f"missing helper script (expected): {helper}")

    cmd = [
        sys.executable,
        str(helper),
        source,
        str(snapshot_dir),
        "--as-of",
        as_of.isoformat(),
        "--",
        *_render_command_tokens_for_manifest(root),
    ]
    subprocess.run(cmd, cwd=root, check=True)
    return root / "data" / "raw_manifest" / f"{source}_{as_of.isoformat()}.json"


def _write_processed_manifest(
    *,
    name: str,
    as_of: date,
    inputs: list[Path],
    outputs: list[Path],
    meta: dict[str, object],
) -> Path:
    root = REPO_ROOT
    helper = root / "scripts" / "make_processed_manifest.py"
    if not helper.exists():
        raise SystemExit(f"missing helper script (expected): {helper}")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tf:
        json.dump(meta, tf, indent=2, sort_keys=True)
        tf.write("\n")
        meta_path = Path(tf.name)

    try:
        cmd: list[str] = [
            sys.executable,
            str(helper),
            name,
            "--as-of",
            as_of.isoformat(),
            "--inputs",
            *[str(p) for p in inputs],
            "--outputs",
            *[str(p) for p in outputs],
            "--meta-json",
            str(meta_path),
            "--",
            *_render_command_tokens_for_manifest(root),
        ]
        subprocess.run(cmd, cwd=root, check=True)
    finally:
        try:
            meta_path.unlink()
        except OSError:
            pass

    return root / "data" / "processed_manifest" / f"{name}_{as_of.isoformat()}.json"


def cmd_discover() -> int:
    out: dict[str, object] = {
        "docs_url": BLOBSCAN_DOCS_URL,
        "api_base_url": BLOBSCAN_API_BASE_URL,
        "stats_timeseries_url": BLOBSCAN_STATS_TIMESERIES_URL,
        "notes": [
            "Blobscan may require auth for some endpoints; prefer public endpoints first.",
            "If API is unavailable or requires auth and no token is available, block and fall back to on-chain aggregates.",
            "See data/samples/blobscan/README.md for project-required fields and policy.",
        ],
    }
    try:
        resp = http_get(BLOBSCAN_API_BASE_URL, timeout_seconds=20, retries=2)
        out["api_status"] = resp.status
    except Exception as exc:
        out["api_status"] = "unreachable"
        out["api_error"] = str(exc)

    try:
        probe_qs = urlencode(
            {
                "timeFrame": "7d",
                "sort": "asc",
                "metrics": ",".join(TIMESERIES_METRICS),
            }
        )
        probe_payload = _safe_http_get_text(f"{BLOBSCAN_STATS_TIMESERIES_URL}?{probe_qs}", timeout_seconds=30)
        probe = json.loads(probe_payload)
        timestamps = probe.get("data", {}).get("timestamps", []) if isinstance(probe, dict) else []
        out["timeseries_probe"] = {
            "status": "ok",
            "metrics": list(TIMESERIES_METRICS),
            "rows": len(timestamps) if isinstance(timestamps, list) else None,
        }
    except Exception as exc:
        out["timeseries_probe"] = {"status": "error", "error": str(exc)}

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_snapshot(*, run_date: str) -> int:
    as_of = _parse_date(run_date, label="run-date")
    run_date_str = as_of.isoformat()

    snapshot_dir = REPO_ROOT / "data" / "raw" / "blobscan" / run_date_str
    ensure_dir(snapshot_dir)

    timeseries_qs = urlencode(
        {
            "timeFrame": "All",
            "sort": "asc",
            "metrics": ",".join(TIMESERIES_METRICS),
        }
    )
    timeseries_url = f"{BLOBSCAN_STATS_TIMESERIES_URL}?{timeseries_qs}"
    timeseries_payload_text = _safe_http_get_text(timeseries_url)
    overall_payload_text = _safe_http_get_text(BLOBSCAN_STATS_OVERALL_URL)

    timeseries_raw_path = snapshot_dir / "stats_timeseries_global.json"
    overall_raw_path = snapshot_dir / "stats_overall.json"
    request_meta_path = snapshot_dir / "request_meta.json"

    write_text_append_only(
        timeseries_raw_path,
        timeseries_payload_text + ("" if timeseries_payload_text.endswith("\n") else "\n"),
        encoding="utf-8",
    )
    write_text_append_only(
        overall_raw_path,
        overall_payload_text + ("" if overall_payload_text.endswith("\n") else "\n"),
        encoding="utf-8",
    )
    request_meta = {
        "source": "blobscan",
        "as_of_utc_date": run_date_str,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "docs_url": BLOBSCAN_DOCS_URL,
        "endpoints": {
            "timeseries": timeseries_url,
            "overall": BLOBSCAN_STATS_OVERALL_URL,
        },
        "timeseries_metrics": list(TIMESERIES_METRICS),
    }
    write_text_append_only(request_meta_path, json.dumps(request_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    raw_manifest_path = _write_raw_manifest(source="blobscan", snapshot_dir=snapshot_dir, as_of=as_of)

    payload = json.loads(timeseries_payload_text, parse_float=Decimal)
    if not isinstance(payload, dict):
        raise SystemExit("Unexpected Blobscan payload shape: top-level JSON must be an object")

    data_obj = payload.get("data")
    if not isinstance(data_obj, dict):
        raise SystemExit("Unexpected Blobscan payload shape: missing data object")

    raw_timestamps = data_obj.get("timestamps")
    if not isinstance(raw_timestamps, list) or any(not isinstance(x, str) for x in raw_timestamps):
        raise SystemExit("Unexpected Blobscan payload shape: data.timestamps must be a list of ISO timestamps")

    series = data_obj.get("series")
    if not isinstance(series, list) or not series:
        raise SystemExit("Unexpected Blobscan payload shape: data.series must be a non-empty list")

    global_series: dict[str, Any] | None = None
    for item in series:
        if not isinstance(item, dict):
            continue
        dimension = item.get("dimension")
        if isinstance(dimension, dict) and dimension.get("type") == "global":
            global_series = item
            break
    if global_series is None:
        raise SystemExit("Blobscan payload missing global dimension series")

    start_idx = global_series.get("startTimestampIdx", 0)
    if not isinstance(start_idx, int) or start_idx < 0:
        raise SystemExit(f"Blobscan global series has invalid startTimestampIdx: {start_idx!r}")

    metrics = global_series.get("metrics")
    if not isinstance(metrics, dict):
        raise SystemExit("Blobscan global series missing metrics object")

    missing_metrics = [m for m in TIMESERIES_METRICS if m not in metrics]
    if missing_metrics:
        raise SystemExit(f"Blobscan global series missing required metrics: {missing_metrics}")

    metric_lengths: set[int] = set()
    for metric_name in TIMESERIES_METRICS:
        values = metrics.get(metric_name)
        if not isinstance(values, list):
            raise SystemExit(f"Blobscan metric {metric_name!r} is not an array")
        metric_lengths.add(len(values))
    if len(metric_lengths) != 1:
        raise SystemExit(f"Blobscan metric arrays have mismatched lengths: {sorted(metric_lengths)}")
    metric_len = next(iter(metric_lengths))

    if start_idx + metric_len > len(raw_timestamps):
        raise SystemExit(
            f"Blobscan series indexing overflow: startTimestampIdx={start_idx}, metric_len={metric_len}, "
            f"timestamps={len(raw_timestamps)}"
        )

    rows: list[dict[str, object]] = []
    seen_dates: set[str] = set()

    for i in range(metric_len):
        ts = raw_timestamps[start_idx + i]
        d = _as_utc_date_from_ts(ts)
        if d > as_of:
            continue
        date_utc = d.isoformat()
        if date_utc in seen_dates:
            raise SystemExit(f"Duplicate date_utc detected in Blobscan payload: {date_utc}")
        seen_dates.add(date_utc)

        avg_blob_gas_price = _parse_decimal(metrics["avgBlobGasPrice"][i], label="avgBlobGasPrice", date_utc=date_utc)
        l1_blob_base_fee_wei = int(avg_blob_gas_price.to_integral_value(rounding=ROUND_HALF_UP))
        if l1_blob_base_fee_wei < 0:
            raise SystemExit(f"l1_blob_base_fee_wei must be >= 0 at date_utc={date_utc}, got {l1_blob_base_fee_wei}")

        l1_blob_gas_used = _parse_int(metrics["totalBlobGasUsed"][i], label="totalBlobGasUsed", date_utc=date_utc)
        l1_blob_tx_count = _parse_int(metrics["totalTransactions"][i], label="totalTransactions", date_utc=date_utc)
        blobs_count = _parse_int(metrics["totalBlobs"][i], label="totalBlobs", date_utc=date_utc)

        rows.append(
            {
                "date_utc": date_utc,
                "l1_blob_base_fee_wei": l1_blob_base_fee_wei,
                "l1_blob_base_fee_gwei": _decimal_to_compact_string(Decimal(l1_blob_base_fee_wei) / Decimal(1_000_000_000)),
                "l1_blob_gas_used": l1_blob_gas_used,
                "l1_blob_tx_count": l1_blob_tx_count,
                "blobs_count": blobs_count,
            }
        )

    if not rows:
        raise SystemExit(f"No Blobscan rows available on or before run date {run_date_str}")

    rows.sort(key=lambda r: str(r["date_utc"]))

    for idx, row in enumerate(rows, start=1):
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in row]
        if missing_cols:
            raise SystemExit(f"row {idx} missing required columns: {missing_cols}")
        date_utc = str(row["date_utc"])
        _parse_date(date_utc, label="date_utc")

        for key in ("l1_blob_base_fee_wei", "l1_blob_gas_used", "l1_blob_tx_count", "blobs_count"):
            value = row.get(key)
            if not isinstance(value, int) or isinstance(value, bool):
                raise SystemExit(f"row {idx} column {key} must be integer, got {value!r}")
            if value < 0:
                raise SystemExit(f"row {idx} column {key} must be >= 0, got {value}")

    ensure_dir(PROCESSED_OUT_PATH.parent)
    processed_columns = [
        "date_utc",
        "l1_blob_base_fee_wei",
        "l1_blob_base_fee_gwei",
        "l1_blob_gas_used",
        "l1_blob_tx_count",
        "blobs_count",
    ]
    with PROCESSED_OUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=processed_columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row[col] for col in processed_columns})

    ensure_dir(SAMPLE_OUT_PATH.parent)
    sample_rows = [
        row
        for row in rows
        if SAMPLE_WINDOW_START <= _parse_date(str(row["date_utc"]), label="sample date_utc") <= SAMPLE_WINDOW_END
    ]
    if not sample_rows:
        raise SystemExit(
            "No Blobscan rows in canonical sample window "
            f"{SAMPLE_WINDOW_START.isoformat()}..{SAMPLE_WINDOW_END.isoformat()}"
        )
    with SAMPLE_OUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=processed_columns, lineterminator="\n")
        writer.writeheader()
        for row in sample_rows:
            writer.writerow({col: row[col] for col in processed_columns})

    processed_manifest_meta: dict[str, object] = {
        "source": {
            "name": "blobscan",
            "docs_url": BLOBSCAN_DOCS_URL,
            "timeseries_endpoint": BLOBSCAN_STATS_TIMESERIES_URL,
            "overall_endpoint": BLOBSCAN_STATS_OVERALL_URL,
            "timeseries_metrics": list(TIMESERIES_METRICS),
        },
        "schema_assertions": {
            "required_columns": list(REQUIRED_COLUMNS),
            "all_columns": processed_columns,
            "integer_columns": ["l1_blob_base_fee_wei", "l1_blob_gas_used", "l1_blob_tx_count", "blobs_count"],
            "base_fee_derivation": "l1_blob_base_fee_wei = round_half_up(avgBlobGasPrice)",
            "gwei_note": "l1_blob_base_fee_gwei is presentation-only, derived from wei.",
        },
        "output_format": {
            "path": str(PROCESSED_OUT_PATH.relative_to(REPO_ROOT)),
            "note": "CSV payload written to .parquet filename for stdlib-only portability (no parquet dependency).",
        },
        "counts": {
            "rows_total": len(rows),
            "rows_sample_window": len(sample_rows),
        },
        "date_range_utc": {
            "start": str(rows[0]["date_utc"]),
            "end": str(rows[-1]["date_utc"]),
        },
        "sample_window_utc": {
            "requested_start": SAMPLE_WINDOW_START.isoformat(),
            "requested_end": SAMPLE_WINDOW_END.isoformat(),
            "actual_start": str(sample_rows[0]["date_utc"]),
            "actual_end": str(sample_rows[-1]["date_utc"]),
        },
        "raw_snapshot": {
            "dir": str(snapshot_dir.relative_to(REPO_ROOT)),
            "files": [
                str(timeseries_raw_path.relative_to(REPO_ROOT)),
                str(overall_raw_path.relative_to(REPO_ROOT)),
                str(request_meta_path.relative_to(REPO_ROOT)),
            ],
        },
    }
    processed_manifest_path = _write_processed_manifest(
        name="blobscan_daily",
        as_of=as_of,
        inputs=[raw_manifest_path],
        outputs=[PROCESSED_OUT_PATH, SAMPLE_OUT_PATH],
        meta=processed_manifest_meta,
    )

    summary = {
        "source": "blobscan",
        "run_date": run_date_str,
        "rows_total": len(rows),
        "rows_sample_window": len(sample_rows),
        "date_start": rows[0]["date_utc"],
        "date_end": rows[-1]["date_utc"],
        "raw_snapshot_dir": str(snapshot_dir),
        "raw_manifest": str(raw_manifest_path),
        "processed_out": str(PROCESSED_OUT_PATH),
        "processed_manifest": str(processed_manifest_path),
        "sample_out": str(SAMPLE_OUT_PATH),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="blobscan_fetch.py")
    p.add_argument("--discover", action="store_true", help="Print endpoint availability notes and exit")
    p.add_argument("--run-date", default=None, help="UTC run date for snapshot folder naming (YYYY-MM-DD)")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.discover:
        return cmd_discover()
    if not args.run_date:
        raise SystemExit("--run-date is required unless --discover is used")
    return cmd_snapshot(run_date=str(args.run_date))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
