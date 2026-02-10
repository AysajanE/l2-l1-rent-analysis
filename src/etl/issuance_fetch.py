from __future__ import annotations

"""Issuance ETL.

Capabilities:
- deterministic sample generation for canonical CI/sample window
- raw snapshot fetch + append-only raw writes from ultrasound.money endpoints
- normalization from input CSV or snapshot directory
- strict contract assertion against contracts/schemas/issuance_daily_v1.yaml
- parquet output + raw/processed manifest generation

Note:
- Ultrasound public APIs do not currently expose an obvious daily *gross issuance* series directly.
  This ETL therefore supports:
  1) canonical local CSV normalization (`--input-csv` / snapshot CSV), and
  2) explicit fallback proxy from `supply-over-time` first differences
     (`--allow-net-from-supply-over-time`) when users opt in.
"""

import argparse
import csv
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "issuance_daily_v1.yaml"

PRIMARY_SOURCE = "ultrasound_money"
PROTOCOL_START_DATE = date(2022, 1, 1)

# Canonical sample window (UTC inclusive) from data/samples/README.md.
SAMPLE_WINDOW_START = date(2024, 2, 20)
SAMPLE_WINDOW_END = date(2024, 4, 30)
SAMPLE_METHOD = "deterministic_sample_v1"

ULTRASOUND_BASE = "https://ultrasound.money"
ULTRASOUND_ENDPOINTS: tuple[tuple[str, str, bool], ...] = (
    ("supply_over_time", "/api/v2/fees/supply-over-time", True),
    ("gauge_rates", "/api/v2/fees/gauge-rates", False),
    ("issuance_estimate", "/api/v2/fees/issuance-estimate", False),
    ("supply_dashboard_analysis", "/api/v2/fees/supply-dashboard-analysis", False),
)


@dataclass(frozen=True)
class ContractField:
    name: str
    nullable: bool


@dataclass(frozen=True)
class IssuanceRow:
    date_utc: date
    issuance_eth: Decimal
    source: str
    method: str | None = None


@dataclass(frozen=True)
class SnapshotFetchResult:
    snapshot_dir: Path
    files_written: list[Path]
    files_reused: list[Path]
    files_failed: dict[str, str]


def _parse_iso_date(value: str, *, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {label} date (expected YYYY-MM-DD): {value!r}") from exc


def _parse_contract_schema(path: Path) -> list[ContractField]:
    if not path.exists():
        raise SystemExit(f"Contract schema not found: {path}")

    name_re = re.compile(r"^\s*-\s*name:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*$")
    nullable_re = re.compile(r"^\s*nullable:\s*(true|false)\s*$", re.IGNORECASE)

    fields: list[ContractField] = []
    current_name: str | None = None
    current_nullable: bool | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        name_match = name_re.match(raw_line)
        if name_match is not None:
            if current_name is not None:
                if current_nullable is None:
                    raise SystemExit(f"Contract schema field missing nullable: {current_name}")
                fields.append(ContractField(name=current_name, nullable=current_nullable))
            current_name = name_match.group(1)
            current_nullable = None
            continue

        nullable_match = nullable_re.match(raw_line)
        if nullable_match is not None and current_name is not None:
            current_nullable = nullable_match.group(1).lower() == "true"

    if current_name is not None:
        if current_nullable is None:
            raise SystemExit(f"Contract schema field missing nullable: {current_name}")
        fields.append(ContractField(name=current_name, nullable=current_nullable))

    if not fields:
        raise SystemExit(f"No fields parsed from contract schema: {path}")

    return fields


def _assert_expected_contract(fields: list[ContractField]) -> None:
    expected: dict[str, bool] = {
        "date_utc": False,
        "issuance_eth": False,
        "source": False,
        "method": True,
    }
    actual = {field.name: field.nullable for field in fields}

    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    nullability_mismatch = sorted(name for name, nullable in expected.items() if actual.get(name) != nullable)

    if missing or extra or nullability_mismatch:
        raise SystemExit(
            "Contract schema does not match supported issuance_daily_v1 fields. "
            f"missing={missing}, extra={extra}, nullability_mismatch={nullability_mismatch}"
        )


def _parse_decimal(value: str, *, label: str) -> Decimal:
    text = value.strip()
    if text == "":
        raise SystemExit(f"Missing {label}")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise SystemExit(f"Invalid decimal for {label}: {value!r}") from exc
    if not parsed.is_finite():
        raise SystemExit(f"Non-finite decimal for {label}: {value!r}")
    return parsed


def _format_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered == "-0":
        return "0"
    return rendered or "0"


def _iter_dates(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        raise SystemExit(f"Invalid date range: start={start_date.isoformat()} end={end_date.isoformat()}")
    out: list[date] = []
    cursor = start_date
    while cursor <= end_date:
        out.append(cursor)
        cursor += timedelta(days=1)
    return out


def _default_sample_out() -> Path:
    return REPO_ROOT / "data" / "samples" / "issuance" / "issuance_daily_sample.csv"


def _default_processed_out() -> Path:
    return REPO_ROOT / "data" / "processed" / "issuance" / "issuance_daily.parquet"


def _default_raw_dir(run_date: date) -> Path:
    return REPO_ROOT / "data" / "raw" / "issuance" / run_date.isoformat()


def _render_command_tokens_for_manifest(root: Path) -> list[str]:
    argv0 = Path(sys.argv[0])
    try:
        script_token = str(argv0.resolve().relative_to(root.resolve()))
    except Exception:
        script_token = sys.argv[0]
    return ["python", script_token, *sys.argv[1:]]


def _write_raw_manifest(*, source: str, snapshot_dir: Path, as_of: date) -> Path:
    helper = REPO_ROOT / "scripts" / "make_raw_manifest.py"
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
        *_render_command_tokens_for_manifest(REPO_ROOT),
    ]
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    return REPO_ROOT / "data" / "raw_manifest" / f"{source}_{as_of.isoformat()}.json"


def _write_processed_manifest(
    *,
    name: str,
    as_of: date,
    inputs: list[Path],
    outputs: list[Path],
    meta: dict[str, object],
) -> Path:
    helper = REPO_ROOT / "scripts" / "make_processed_manifest.py"
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
            *_render_command_tokens_for_manifest(REPO_ROOT),
        ]
        subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    finally:
        try:
            meta_path.unlink()
        except OSError:
            pass

    return REPO_ROOT / "data" / "processed_manifest" / f"{name}_{as_of.isoformat()}.json"


def _build_deterministic_sample_rows(*, method_override: str | None = None) -> list[IssuanceRow]:
    rows: list[IssuanceRow] = []
    weekly_adjustments = (
        Decimal("0.000000"),
        Decimal("1.750000"),
        Decimal("-0.875000"),
        Decimal("2.500000"),
        Decimal("-1.250000"),
        Decimal("0.625000"),
        Decimal("-0.500000"),
    )
    base = Decimal("1715.000000")
    drift_per_day = Decimal("0.437500")
    method = (method_override.strip() if method_override is not None else SAMPLE_METHOD) or None

    for idx, day in enumerate(_iter_dates(SAMPLE_WINDOW_START, SAMPLE_WINDOW_END)):
        issuance_eth = (base + (drift_per_day * Decimal(idx)) + weekly_adjustments[idx % len(weekly_adjustments)]).quantize(
            Decimal("0.000001")
        )
        rows.append(
            IssuanceRow(
                date_utc=day,
                issuance_eth=issuance_eth,
                source=PRIMARY_SOURCE,
                method=method,
            )
        )
    return rows


def _http_get_json(url: str, *, timeout_seconds: int, retries: int) -> Any:
    headers = {
        "Accept": "application/json",
        "User-Agent": "l2-l1-rent-analysis/issuance_fetch.py",
    }
    last_exc: Exception | None = None
    for attempt in range(max(0, retries) + 1):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:  # nosec B310
                body = resp.read().decode("utf-8")
            return json.loads(body)
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(1.0 * (2**attempt))
                continue
            break
    if last_exc is None:
        raise SystemExit(f"fetch failed with unknown error: {url}")
    raise SystemExit(f"fetch failed for {url}: {last_exc}")


def _write_json_append_only_or_reuse(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return "reused"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return "written"


def _read_json(path: Path, *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} is not valid JSON: {path}") from exc


def _copy_file_append_only_or_reuse(src: Path, dst: Path) -> str:
    if not src.exists() or not src.is_file():
        raise SystemExit(f"input CSV not found for snapshot copy: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return "reused"
    shutil.copyfile(src, dst)
    return "written"


def _fetch_ultrasound_snapshot(
    *,
    run_date: date,
    raw_dir: Path,
    timeout_seconds: int,
    retries: int,
) -> SnapshotFetchResult:
    raw_dir.mkdir(parents=True, exist_ok=True)

    files_written: list[Path] = []
    files_reused: list[Path] = []
    files_failed: dict[str, str] = {}

    status_meta: dict[str, object] = {
        "run_date_utc": run_date.isoformat(),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "endpoints": {},
    }

    for key, endpoint_path, required in ULTRASOUND_ENDPOINTS:
        out_path = raw_dir / f"ultrasound_{key}.json"
        url = f"{ULTRASOUND_BASE}{endpoint_path}"
        endpoint_record: dict[str, object] = {
            "key": key,
            "url": url,
            "required": required,
            "file": str(out_path.relative_to(REPO_ROOT)),
        }
        if out_path.exists():
            endpoint_record["status"] = "reused"
            files_reused.append(out_path)
            status_meta["endpoints"][key] = endpoint_record
            continue
        try:
            payload = _http_get_json(url, timeout_seconds=timeout_seconds, retries=retries)
        except SystemExit as exc:
            endpoint_record["status"] = "failed"
            endpoint_record["error"] = str(exc)
            files_failed[key] = str(exc)
            status_meta["endpoints"][key] = endpoint_record
            if required:
                raise
            continue
        endpoint_record["status"] = _write_json_append_only_or_reuse(out_path, payload)
        files_written.append(out_path)
        status_meta["endpoints"][key] = endpoint_record

    meta_path = raw_dir / "snapshot_fetch_meta.json"
    if _write_json_append_only_or_reuse(meta_path, status_meta) == "written":
        files_written.append(meta_path)
    else:
        files_reused.append(meta_path)

    return SnapshotFetchResult(
        snapshot_dir=raw_dir,
        files_written=files_written,
        files_reused=files_reused,
        files_failed=files_failed,
    )


def _resolve_snapshot_csv(snapshot_dir: Path) -> Path | None:
    preferred_candidates = [
        snapshot_dir / "issuance_daily.csv",
        snapshot_dir / "issuance.csv",
        snapshot_dir / "daily_issuance.csv",
        snapshot_dir / "input_issuance_daily.csv",
    ]
    for candidate in preferred_candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    csv_candidates = sorted(p for p in snapshot_dir.glob("*.csv") if p.is_file())
    if len(csv_candidates) == 1:
        return csv_candidates[0]
    if len(csv_candidates) > 1:
        rels = [str(p.relative_to(snapshot_dir)) for p in csv_candidates]
        raise SystemExit(
            "Ambiguous snapshot directory: multiple CSV files found. "
            f"Provide --input-csv explicitly. candidates={rels}"
        )
    return None


def _load_rows_from_csv(input_csv: Path, *, source_override: str | None, method_override: str | None) -> list[IssuanceRow]:
    if not input_csv.exists() or not input_csv.is_file():
        raise SystemExit(f"Input CSV not found: {input_csv}")

    rows: list[IssuanceRow] = []
    seen_dates: set[date] = set()

    with input_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit(f"Input CSV missing header row: {input_csv}")

        fieldnames = {name.strip() for name in reader.fieldnames if name is not None}
        required_min = {"date_utc", "issuance_eth"}
        missing = sorted(required_min - fieldnames)
        if missing:
            raise SystemExit(f"Input CSV missing required columns: {missing}")

        has_source_column = "source" in fieldnames
        if not has_source_column and source_override is None:
            raise SystemExit("Input CSV missing 'source' column; provide --source to set a deterministic source.")

        has_method_column = "method" in fieldnames

        for row_index, raw_row in enumerate(reader, start=2):
            date_text = (raw_row.get("date_utc") or "").strip()
            issuance_text = (raw_row.get("issuance_eth") or "").strip()

            parsed_date = _parse_iso_date(date_text, label=f"date_utc (row {row_index})")
            if parsed_date in seen_dates:
                raise SystemExit(f"Duplicate date_utc detected (row {row_index}): {parsed_date.isoformat()}")
            seen_dates.add(parsed_date)

            parsed_issuance = _parse_decimal(issuance_text, label=f"issuance_eth (row {row_index})")
            source_value = source_override if source_override is not None else (raw_row.get("source") or "").strip()
            if source_value == "":
                raise SystemExit(f"Missing source (row {row_index})")

            if method_override is not None:
                method_value = method_override
            elif has_method_column:
                method_value = (raw_row.get("method") or "").strip() or None
            else:
                method_value = None

            rows.append(
                IssuanceRow(
                    date_utc=parsed_date,
                    issuance_eth=parsed_issuance,
                    source=source_value,
                    method=method_value,
                )
            )

    if not rows:
        raise SystemExit(f"Input CSV produced zero rows: {input_csv}")
    rows.sort(key=lambda r: r.date_utc)
    return rows


def _parse_row_date(raw: dict[str, object], *, row_label: str) -> date:
    for key in ("date_utc", "date", "day"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip() != "":
            return _parse_iso_date(v.strip(), label=f"{row_label}.{key}")

    timestamp = raw.get("timestamp")
    if isinstance(timestamp, str) and timestamp.strip():
        text = timestamp.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).date()
        except ValueError as exc:
            raise SystemExit(f"Invalid {row_label}.timestamp datetime: {timestamp!r}") from exc
    if isinstance(raw.get("t"), (int, float)):
        return datetime.fromtimestamp(float(raw["t"]), tz=timezone.utc).date()

    raise SystemExit(f"Could not infer date for {row_label}")


def _extract_daily_issuance_rows_from_json(
    payload: Any,
    *,
    source_override: str | None,
    method_override: str | None,
) -> list[IssuanceRow]:
    candidates: list[dict[str, object]] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                candidates.append(item)
    elif isinstance(payload, dict):
        for key in ("issuance_by_day", "issuanceByDay", "daily_issuance", "dailyIssuance"):
            seq = payload.get(key)
            if isinstance(seq, list):
                for item in seq:
                    if isinstance(item, dict):
                        candidates.append(item)

    out: list[IssuanceRow] = []
    seen_dates: set[date] = set()
    for idx, row in enumerate(candidates):
        issuance_raw: object | None = None
        for value_key in ("issuance_eth", "issuance", "gross_issuance_eth", "consensus_issuance_eth"):
            if value_key in row:
                issuance_raw = row[value_key]
                break
        if issuance_raw is None:
            continue
        issuance_text = str(issuance_raw)
        parsed_date = _parse_row_date(row, row_label=f"json_row_{idx}")
        if parsed_date in seen_dates:
            raise SystemExit(f"Duplicate date detected while parsing JSON payload: {parsed_date.isoformat()}")
        seen_dates.add(parsed_date)

        source_value = source_override
        if source_value is None:
            source_raw = row.get("source")
            source_value = source_raw.strip() if isinstance(source_raw, str) else PRIMARY_SOURCE
        method_value = method_override
        if method_value is None:
            m = row.get("method")
            method_value = m.strip() if isinstance(m, str) and m.strip() else None

        out.append(
            IssuanceRow(
                date_utc=parsed_date,
                issuance_eth=_parse_decimal(issuance_text, label=f"json issuance ({parsed_date.isoformat()})"),
                source=source_value,
                method=method_value,
            )
        )

    out.sort(key=lambda r: r.date_utc)
    return out


def _rows_from_supply_over_time_proxy(
    payload: Any,
    *,
    source_override: str | None,
    method_override: str | None,
) -> list[IssuanceRow]:
    if not isinstance(payload, dict):
        raise SystemExit("supply-over-time payload must be a JSON object")
    series = payload.get("since_burn")
    if not isinstance(series, list):
        raise SystemExit("supply-over-time payload missing `since_burn` list")

    day_to_supply: dict[date, Decimal] = {}
    for i, item in enumerate(series):
        if not isinstance(item, dict):
            continue
        ts = item.get("timestamp")
        supply = item.get("supply")
        if not isinstance(ts, str):
            continue
        if isinstance(supply, bool) or not isinstance(supply, (int, float, str)):
            continue
        try:
            parsed_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        day = parsed_dt.date()
        if day not in day_to_supply:
            day_to_supply[day] = _parse_decimal(str(supply), label=f"supply-over-time supply row {i}")

    days_sorted = sorted(day_to_supply.keys())
    if len(days_sorted) < 2:
        raise SystemExit("supply-over-time proxy requires at least two daily points")

    method = (method_override.strip() if method_override is not None else "") or "net_supply_delta_from_supply_over_time_proxy"
    source = (source_override.strip() if source_override is not None else "") or PRIMARY_SOURCE

    out: list[IssuanceRow] = []
    for i in range(1, len(days_sorted)):
        day = days_sorted[i]
        prev_day = days_sorted[i - 1]
        delta = day_to_supply[day] - day_to_supply[prev_day]
        out.append(IssuanceRow(date_utc=day, issuance_eth=delta, source=source, method=method))
    return out


def _load_rows_from_snapshot_dir(
    snapshot_dir: Path,
    *,
    source_override: str | None,
    method_override: str | None,
    allow_net_from_supply_over_time: bool,
) -> list[IssuanceRow]:
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        raise SystemExit(f"--from-snapshot directory not found: {snapshot_dir}")

    snapshot_csv = _resolve_snapshot_csv(snapshot_dir)
    if snapshot_csv is not None:
        return _load_rows_from_csv(
            snapshot_csv,
            source_override=source_override,
            method_override=method_override,
        )

    json_candidates = sorted(p for p in snapshot_dir.glob("*.json") if p.is_file())
    for p in json_candidates:
        payload = _read_json(p, label="snapshot JSON")
        parsed_rows = _extract_daily_issuance_rows_from_json(
            payload,
            source_override=source_override,
            method_override=method_override,
        )
        if parsed_rows:
            return parsed_rows

    if allow_net_from_supply_over_time:
        supply_path = snapshot_dir / "ultrasound_supply_over_time.json"
        if not supply_path.exists():
            raise SystemExit(
                "No daily issuance CSV/JSON found in snapshot and fallback requested, "
                f"but missing {supply_path}"
            )
        payload = _read_json(supply_path, label="ultrasound supply-over-time snapshot")
        return _rows_from_supply_over_time_proxy(
            payload,
            source_override=source_override,
            method_override=method_override,
        )

    raise SystemExit(
        "Could not find an issuance daily series in snapshot. Provide --input-csv or enable "
        "--allow-net-from-supply-over-time for explicit proxy mode."
    )


def _filter_rows_by_window(rows: list[IssuanceRow], *, start_date: date, end_date: date) -> list[IssuanceRow]:
    filtered = [row for row in rows if start_date <= row.date_utc <= end_date]
    filtered.sort(key=lambda r: r.date_utc)
    if not filtered:
        raise SystemExit(
            f"Date window filter produced zero rows: start={start_date.isoformat()}, end={end_date.isoformat()}"
        )
    return filtered


def _validate_rows(
    rows: list[IssuanceRow],
    *,
    fields: list[ContractField],
    allow_negative_issuance: bool,
) -> None:
    required = {field.name for field in fields if not field.nullable}
    optional = {field.name for field in fields if field.nullable}
    if required != {"date_utc", "issuance_eth", "source"}:
        raise SystemExit(f"Unexpected required field set from contract: {sorted(required)}")
    if optional != {"method"}:
        raise SystemExit(f"Unexpected optional field set from contract: {sorted(optional)}")

    seen_dates: set[date] = set()
    sources: set[str] = set()
    for row in rows:
        if row.date_utc in seen_dates:
            raise SystemExit(f"Duplicate date_utc detected after normalization: {row.date_utc.isoformat()}")
        seen_dates.add(row.date_utc)
        if not row.issuance_eth.is_finite():
            raise SystemExit(f"Non-finite issuance_eth for date {row.date_utc.isoformat()}")
        if not allow_negative_issuance and row.issuance_eth < Decimal("0"):
            raise SystemExit(
                "Negative issuance_eth detected while gross issuance mode is required. "
                f"date={row.date_utc.isoformat()} issuance_eth={_format_decimal(row.issuance_eth)}"
            )
        if row.source.strip() == "":
            raise SystemExit(f"Empty source for date {row.date_utc.isoformat()}")
        if row.method is not None and row.method.strip() == "":
            raise SystemExit(f"Empty method for date {row.date_utc.isoformat()}")
        sources.add(row.source)
    if len(sources) != 1:
        raise SystemExit(f"source must be consistent across rows; found: {sorted(sources)}")


def _write_sample_csv(path: Path, rows: list[IssuanceRow], *, overwrite: bool) -> str:
    include_method = any(row.method is not None for row in rows)
    fieldnames = ["date_utc", "issuance_eth", "source"] + (["method"] if include_method else [])
    rendered_lines = [",".join(fieldnames)]
    for row in rows:
        parts = [
            row.date_utc.isoformat(),
            _format_decimal(row.issuance_eth),
            row.source,
        ]
        if include_method:
            parts.append(row.method or "")
        rendered_lines.append(",".join(parts))
    rendered = "\n".join(rendered_lines) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == rendered:
            return "reused"
        if not overwrite:
            raise SystemExit(f"Refusing to overwrite existing sample (use --overwrite): {path}")
    path.write_text(rendered, encoding="utf-8")
    return "written"


def _write_parquet(path: Path, rows: list[IssuanceRow], *, overwrite: bool) -> str:
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "pyarrow is required to write parquet output. Install it (or set PYTHONPATH to include it) and rerun."
        ) from exc

    if path.exists() and not overwrite:
        raise SystemExit(f"Refusing to overwrite existing processed parquet (use --overwrite): {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pydict(
        {
            "date_utc": [row.date_utc.isoformat() for row in rows],
            "issuance_eth": [float(row.issuance_eth) for row in rows],
            "source": [row.source for row in rows],
            "method": [row.method for row in rows],
        },
        schema=pa.schema(
            [
                pa.field("date_utc", pa.string(), nullable=False),
                pa.field("issuance_eth", pa.float64(), nullable=False),
                pa.field("source", pa.string(), nullable=False),
                pa.field("method", pa.string(), nullable=True),
            ]
        ),
    )
    pq.write_table(table, path, compression="zstd")
    return "written"


def _resolve_path(value: str, *, root: Path) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (root / p)


def _infer_as_of(run_date: date | None, from_snapshot: Path | None) -> date:
    if run_date is not None:
        return run_date
    if from_snapshot is not None:
        name = from_snapshot.name
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", name):
            return _parse_iso_date(name, label="from-snapshot folder")
    return date.today()


def _rows_for_sample_window(rows: list[IssuanceRow]) -> list[IssuanceRow]:
    out = [row for row in rows if SAMPLE_WINDOW_START <= row.date_utc <= SAMPLE_WINDOW_END]
    out.sort(key=lambda r: r.date_utc)
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="issuance_fetch.py")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--sample", action="store_true", help="Write deterministic canonical sample window CSV")
    mode_group.add_argument("--input-csv", default=None, help="Normalize and validate a local issuance CSV")
    mode_group.add_argument("--from-snapshot", default=None, help="Normalize from an existing raw snapshot directory")

    parser.add_argument("--run-date", default=None, help="UTC run date for snapshot folder naming (YYYY-MM-DD)")
    parser.add_argument(
        "--allow-net-from-supply-over-time",
        action="store_true",
        help="Explicitly allow proxy mode: derive first differences from ultrasound supply-over-time.",
    )
    parser.add_argument("--source", default=None, help="Override source for emitted rows")
    parser.add_argument("--method", default=None, help="Override method for emitted rows")
    parser.add_argument("--start-date", default=PROTOCOL_START_DATE.isoformat(), help="Start date (UTC) for output rows")
    parser.add_argument("--end-date", default=None, help="End date (UTC) for output rows")
    parser.add_argument("--raw-dir", default=None, help="Raw snapshot directory (default data/raw/issuance/<run-date>)")
    parser.add_argument("--out-processed", default="data/processed/issuance/issuance_daily.parquet")
    parser.add_argument("--write-sample", action="store_true", help="Write sample CSV from current rows/window")
    parser.add_argument("--sample-out", default="data/samples/issuance/issuance_daily_sample.csv")
    parser.add_argument("--write-raw-manifest", action="store_true", help="Write raw manifest via scripts/make_raw_manifest.py")
    parser.add_argument(
        "--write-processed-manifest",
        action="store_true",
        help="Write processed manifest via scripts/make_processed_manifest.py",
    )
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing existing processed/sample outputs")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--retries", type=int, default=3)
    return parser


def _run_sample_mode(args: argparse.Namespace, contract_fields: list[ContractField]) -> int:
    rows = _build_deterministic_sample_rows(method_override=args.method)
    _validate_rows(rows, fields=contract_fields, allow_negative_issuance=False)
    sample_out = _resolve_path(str(args.sample_out), root=REPO_ROOT)
    sample_status = _write_sample_csv(sample_out, rows, overwrite=bool(args.overwrite))
    summary = {
        "ok": True,
        "mode": "sample",
        "sample_out": str(sample_out),
        "sample_status": sample_status,
        "rows": len(rows),
        "date_start_utc": rows[0].date_utc.isoformat(),
        "date_end_utc": rows[-1].date_utc.isoformat(),
        "source_values": sorted({row.source for row in rows}),
        "method_values": sorted({row.method for row in rows if row.method is not None}),
        "contract_schema": str(CONTRACT_SCHEMA_PATH),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    contract_fields = _parse_contract_schema(CONTRACT_SCHEMA_PATH)
    _assert_expected_contract(contract_fields)

    if args.sample:
        return _run_sample_mode(args, contract_fields)

    run_date = _parse_iso_date(args.run_date, label="run_date") if args.run_date else None
    start_date = _parse_iso_date(str(args.start_date), label="start_date")
    end_date = _parse_iso_date(str(args.end_date), label="end_date") if args.end_date else (run_date or date.today())
    if end_date < start_date:
        raise SystemExit(f"Invalid date window: start={start_date.isoformat()} end={end_date.isoformat()}")

    source_override = args.source.strip() if isinstance(args.source, str) and args.source.strip() else None
    method_override = args.method.strip() if isinstance(args.method, str) and args.method.strip() else None

    snapshot_result: SnapshotFetchResult | None = None
    snapshot_dir: Path | None = None
    from_snapshot: Path | None = None
    input_csv: Path | None = None
    copied_input_snapshot_path: Path | None = None

    if args.from_snapshot:
        from_snapshot = _resolve_path(str(args.from_snapshot), root=REPO_ROOT)
        snapshot_dir = from_snapshot

    if run_date is not None and snapshot_dir is None:
        raw_dir = _resolve_path(args.raw_dir, root=REPO_ROOT) if args.raw_dir else _default_raw_dir(run_date)
        snapshot_result = _fetch_ultrasound_snapshot(
            run_date=run_date,
            raw_dir=raw_dir,
            timeout_seconds=int(args.timeout_seconds),
            retries=int(args.retries),
        )
        snapshot_dir = snapshot_result.snapshot_dir

    if args.input_csv:
        input_csv = _resolve_path(str(args.input_csv), root=REPO_ROOT)
        rows = _load_rows_from_csv(
            input_csv,
            source_override=source_override,
            method_override=method_override,
        )
        if snapshot_dir is not None:
            copied_input_snapshot_path = snapshot_dir / "input_issuance_daily.csv"
            _copy_file_append_only_or_reuse(input_csv, copied_input_snapshot_path)
    else:
        if snapshot_dir is None:
            raise SystemExit(
                "Provide one of: --sample, --input-csv, --from-snapshot, or --run-date."
            )
        rows = _load_rows_from_snapshot_dir(
            snapshot_dir,
            source_override=source_override,
            method_override=method_override,
            allow_net_from_supply_over_time=bool(args.allow_net_from_supply_over_time),
        )

    rows = _filter_rows_by_window(rows, start_date=start_date, end_date=end_date)
    _validate_rows(
        rows,
        fields=contract_fields,
        allow_negative_issuance=bool(args.allow_net_from_supply_over_time),
    )

    out_processed = _resolve_path(str(args.out_processed), root=REPO_ROOT)
    parquet_status = _write_parquet(out_processed, rows, overwrite=bool(args.overwrite))

    sample_rows = _rows_for_sample_window(rows)
    sample_out = _resolve_path(str(args.sample_out), root=REPO_ROOT)
    sample_status: str | None = None
    if args.write_sample:
        if not sample_rows:
            raise SystemExit(
                "Sample window filter produced zero rows; cannot write sample. "
                f"window={SAMPLE_WINDOW_START.isoformat()}..{SAMPLE_WINDOW_END.isoformat()}"
            )
        sample_status = _write_sample_csv(sample_out, sample_rows, overwrite=bool(args.overwrite))

    as_of = _infer_as_of(run_date, from_snapshot)

    raw_manifest_path: Path | None = None
    if args.write_raw_manifest:
        if snapshot_dir is None:
            raise SystemExit("--write-raw-manifest requires --run-date or --from-snapshot")
        raw_manifest_path = _write_raw_manifest(
            source="issuance",
            snapshot_dir=snapshot_dir.relative_to(REPO_ROOT) if snapshot_dir.is_absolute() else snapshot_dir,
            as_of=as_of,
        )

    processed_manifest_path: Path | None = None
    if args.write_processed_manifest:
        manifest_inputs: list[Path] = []
        if raw_manifest_path is not None and raw_manifest_path.exists():
            manifest_inputs.append(raw_manifest_path)
        else:
            candidate_raw_manifest = REPO_ROOT / "data" / "raw_manifest" / f"issuance_{as_of.isoformat()}.json"
            if candidate_raw_manifest.exists():
                manifest_inputs.append(candidate_raw_manifest)
        if copied_input_snapshot_path is not None:
            manifest_inputs.append(copied_input_snapshot_path)
        elif input_csv is not None:
            manifest_inputs.append(input_csv)
        elif snapshot_dir is not None:
            manifest_inputs.append(snapshot_dir)
        manifest_inputs.append(CONTRACT_SCHEMA_PATH)

        manifest_outputs = [out_processed]
        if args.write_sample and sample_status is not None:
            manifest_outputs.append(sample_out)

        meta = {
            "source_policy": {
                "primary": PRIMARY_SOURCE,
                "proxy_mode_enabled": bool(args.allow_net_from_supply_over_time),
            },
            "date_window_utc": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "sample_window_utc": {
                "start": SAMPLE_WINDOW_START.isoformat(),
                "end": SAMPLE_WINDOW_END.isoformat(),
            },
            "rows_emitted": len(rows),
            "sample_rows_emitted": len(sample_rows),
            "source_values": sorted({row.source for row in rows}),
            "method_values": sorted({row.method for row in rows if row.method is not None}),
            "contract_schema": str(CONTRACT_SCHEMA_PATH.relative_to(REPO_ROOT)),
            "snapshot": (
                {
                    "snapshot_dir": str(snapshot_dir.relative_to(REPO_ROOT) if snapshot_dir.is_absolute() else snapshot_dir),
                    "files_written": (
                        [str(p.relative_to(REPO_ROOT)) for p in snapshot_result.files_written]
                        if snapshot_result is not None
                        else []
                    ),
                    "files_reused": (
                        [str(p.relative_to(REPO_ROOT)) for p in snapshot_result.files_reused]
                        if snapshot_result is not None
                        else []
                    ),
                    "files_failed": snapshot_result.files_failed if snapshot_result is not None else {},
                }
                if snapshot_dir is not None
                else None
            ),
        }
        processed_manifest_path = _write_processed_manifest(
            name="issuance_daily",
            as_of=as_of,
            inputs=[p.relative_to(REPO_ROOT) if p.is_absolute() else p for p in manifest_inputs],
            outputs=[p.relative_to(REPO_ROOT) if p.is_absolute() else p for p in manifest_outputs],
            meta=meta,
        )

    summary = {
        "ok": True,
        "mode": "full",
        "as_of_utc_date": as_of.isoformat(),
        "rows": len(rows),
        "date_start_utc": rows[0].date_utc.isoformat(),
        "date_end_utc": rows[-1].date_utc.isoformat(),
        "source_values": sorted({row.source for row in rows}),
        "method_values": sorted({row.method for row in rows if row.method is not None}),
        "allow_net_from_supply_over_time": bool(args.allow_net_from_supply_over_time),
        "snapshot_dir": str(snapshot_dir) if snapshot_dir is not None else None,
        "input_csv": str(input_csv) if input_csv is not None else None,
        "out_processed": str(out_processed),
        "parquet_status": parquet_status,
        "sample": {
            "write_sample": bool(args.write_sample),
            "rows": len(sample_rows),
            "out": str(sample_out) if args.write_sample else None,
            "status": sample_status,
        },
        "raw_manifest": str(raw_manifest_path) if raw_manifest_path else None,
        "processed_manifest": str(processed_manifest_path) if processed_manifest_path else None,
        "manifest_command_example": "python scripts/make_processed_manifest.py issuance_daily --as-of YYYY-MM-DD --inputs ... --outputs ... -- -- python src/etl/issuance_fetch.py ...",
        "contract_schema": str(CONTRACT_SCHEMA_PATH),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
