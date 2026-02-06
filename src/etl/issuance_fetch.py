from __future__ import annotations

"""Issuance ETL CLI (stdlib-only).

Modes:
- Sample mode: deterministic canonical-window output for tests/CI.
- Local-input mode: reproducible normalization from local CSV/snapshot paths.

Contract enforcement is driven by contracts/schemas/issuance_daily_v1.yaml and fails fast on
missing/invalid required fields.
"""

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "issuance_daily_v1.yaml"

# Canonical sample window (UTC inclusive) from data/samples/README.md.
SAMPLE_WINDOW_START = date(2024, 2, 20)
SAMPLE_WINDOW_END = date(2024, 4, 30)
SAMPLE_SOURCE = "ultrasound_money"
SAMPLE_METHOD = "deterministic_sample_v1"


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


def _build_deterministic_sample_rows() -> list[IssuanceRow]:
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

    for idx, day in enumerate(_iter_dates(SAMPLE_WINDOW_START, SAMPLE_WINDOW_END)):
        issuance_eth = (base + (drift_per_day * Decimal(idx)) + weekly_adjustments[idx % len(weekly_adjustments)]).quantize(
            Decimal("0.000001")
        )
        rows.append(
            IssuanceRow(
                date_utc=day,
                issuance_eth=issuance_eth,
                source=SAMPLE_SOURCE,
                method=SAMPLE_METHOD,
            )
        )

    return rows


def _resolve_snapshot_csv(snapshot_path: Path) -> Path:
    if snapshot_path.is_file():
        if snapshot_path.suffix.lower() != ".csv":
            raise SystemExit(f"--snapshot-path file must be a CSV: {snapshot_path}")
        return snapshot_path

    if not snapshot_path.exists():
        raise SystemExit(f"Snapshot path not found: {snapshot_path}")

    if not snapshot_path.is_dir():
        raise SystemExit(f"--snapshot-path must be a CSV file or directory: {snapshot_path}")

    preferred_candidates = [
        snapshot_path / "issuance_daily.csv",
        snapshot_path / "issuance.csv",
        snapshot_path / "daily_issuance.csv",
    ]
    for candidate in preferred_candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    csv_candidates = sorted(p for p in snapshot_path.glob("*.csv") if p.is_file())
    if len(csv_candidates) == 1:
        return csv_candidates[0]
    if len(csv_candidates) == 0:
        raise SystemExit(f"No CSV files found in snapshot directory: {snapshot_path}")

    rels = [str(p.relative_to(snapshot_path)) for p in csv_candidates]
    raise SystemExit(
        "Ambiguous snapshot directory: multiple CSV files found. "
        f"Provide --input-csv explicitly. candidates={rels}"
    )


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

            method_value: str | None
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


def _validate_rows(rows: list[IssuanceRow], *, fields: list[ContractField]) -> None:
    required = {field.name for field in fields if not field.nullable}
    optional = {field.name for field in fields if field.nullable}

    if required != {"date_utc", "issuance_eth", "source"}:
        raise SystemExit(f"Unexpected required field set from contract: {sorted(required)}")
    if optional != {"method"}:
        raise SystemExit(f"Unexpected optional field set from contract: {sorted(optional)}")

    seen_dates: set[date] = set()
    for row in rows:
        if row.date_utc in seen_dates:
            raise SystemExit(f"Duplicate date_utc detected after normalization: {row.date_utc.isoformat()}")
        seen_dates.add(row.date_utc)

        if not row.issuance_eth.is_finite():
            raise SystemExit(f"Non-finite issuance_eth for date {row.date_utc.isoformat()}")
        if row.source.strip() == "":
            raise SystemExit(f"Empty source for date {row.date_utc.isoformat()}")
        if row.method is not None and row.method.strip() == "":
            raise SystemExit(f"Empty method for date {row.date_utc.isoformat()}")


def _write_output_csv(path: Path, rows: list[IssuanceRow], *, overwrite: bool) -> tuple[list[str], bool]:
    include_method = any(row.method is not None for row in rows)
    fieldnames = ["date_utc", "issuance_eth", "source"] + (["method"] if include_method else [])

    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    try:
        with path.open(mode, encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                record = {
                    "date_utc": row.date_utc.isoformat(),
                    "issuance_eth": _format_decimal(row.issuance_eth),
                    "source": row.source,
                }
                if include_method:
                    record["method"] = row.method or ""
                writer.writerow(record)
    except FileExistsError as exc:
        raise SystemExit(f"Refusing to overwrite existing file: {path} (use --overwrite to replace)") from exc

    return fieldnames, include_method


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="issuance_fetch.py")

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--sample", action="store_true", help="Emit deterministic canonical sample window rows")
    mode_group.add_argument("--input-csv", default=None, help="Normalize and validate a local input CSV")
    mode_group.add_argument("--snapshot-path", default=None, help="Normalize from a snapshot CSV file or directory")

    parser.add_argument("--source", default=None, help="Override source for local-input rows (required if input lacks source)")
    parser.add_argument("--method", default=None, help="Override method for all emitted rows")
    parser.add_argument("--out-csv", default=None, help="Output CSV path")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing output file")

    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    contract_fields = _parse_contract_schema(CONTRACT_SCHEMA_PATH)
    _assert_expected_contract(contract_fields)

    mode: str
    input_csv_path: Path | None = None

    if args.sample:
        mode = "sample"
        rows = _build_deterministic_sample_rows()
    else:
        mode = "local_input"
        if args.input_csv:
            input_csv_path = Path(args.input_csv)
        elif args.snapshot_path:
            input_csv_path = _resolve_snapshot_csv(Path(args.snapshot_path))
        else:
            raise SystemExit("One of --sample, --input-csv, or --snapshot-path is required")

        rows = _load_rows_from_csv(
            input_csv_path,
            source_override=(args.source.strip() if args.source is not None else None),
            method_override=(args.method.strip() if args.method is not None else None),
        )

    if args.sample and args.method is not None:
        overridden_method = args.method.strip()
        rows = [
            IssuanceRow(
                date_utc=row.date_utc,
                issuance_eth=row.issuance_eth,
                source=row.source,
                method=overridden_method or None,
            )
            for row in rows
        ]

    _validate_rows(rows, fields=contract_fields)

    if args.out_csv:
        out_path = Path(args.out_csv)
    else:
        if mode == "sample":
            out_path = REPO_ROOT / "data" / "samples" / "issuance" / "issuance_daily_sample.csv"
        else:
            out_path = REPO_ROOT / "data" / "processed" / "issuance" / "issuance_daily.csv"

    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path

    fieldnames, include_method = _write_output_csv(out_path, rows, overwrite=bool(args.overwrite))

    summary = {
        "ok": True,
        "mode": mode,
        "input_csv": str(input_csv_path) if input_csv_path is not None else None,
        "out_csv": str(out_path),
        "rows": len(rows),
        "date_start_utc": rows[0].date_utc.isoformat(),
        "date_end_utc": rows[-1].date_utc.isoformat(),
        "source_values": sorted({row.source for row in rows}),
        "output_columns": fieldnames,
        "method_column_included": include_method,
        "contract_schema": str(CONTRACT_SCHEMA_PATH),
    }
    if mode == "sample":
        summary["sample_window_utc"] = {
            "start": SAMPLE_WINDOW_START.isoformat(),
            "end": SAMPLE_WINDOW_END.isoformat(),
        }

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
