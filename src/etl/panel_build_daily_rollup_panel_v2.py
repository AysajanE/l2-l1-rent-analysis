from __future__ import annotations

"""Build the contract v2 enriched daily rollup panel (CSV-only; stdlib-only).

The builder extends a v1 daily panel with optional enrichment inputs:
- rollup-level decomposition (`date_utc`, `rollup_id`)
- L1 regime fields (`date_utc` or `date_utc`, `rollup_id`)
- prices (`date_utc` or `date_utc`, `rollup_id`)
- issuance (`date_utc` or `date_utc`, `rollup_id`)

`--sample` mode is fully deterministic and uses only committed sample assets.
No network calls are performed.
"""

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


EXPECTED_V2_FIELDS = (
    "date_utc",
    "rollup_id",
    "l2_fees_eth",
    "rent_paid_eth",
    "profit_eth",
    "txcount",
    "rent_base_fee_burn_eth",
    "rent_blob_fee_burn_eth",
    "rent_priority_fee_eth",
    "rent_blob_fee_burn_wei",
    "rollup_blob_gas_used",
    "l1_base_fee_per_gas_wei",
    "l1_blob_base_fee_wei",
    "l1_blob_gas_used",
    "eth_usd_close",
    "issuance_eth",
    "registry_version",
)

EXPECTED_V2_REQUIRED_FIELDS = (
    "date_utc",
    "rollup_id",
    "l2_fees_eth",
    "rent_paid_eth",
    "l1_base_fee_per_gas_wei",
)

EXPECTED_V2_TYPES = {
    "date_utc": "date",
    "rollup_id": "string",
    "l2_fees_eth": "number",
    "rent_paid_eth": "number",
    "profit_eth": "number",
    "txcount": "integer",
    "rent_base_fee_burn_eth": "number",
    "rent_blob_fee_burn_eth": "number",
    "rent_priority_fee_eth": "number",
    "rent_blob_fee_burn_wei": "integer",
    "rollup_blob_gas_used": "integer",
    "l1_base_fee_per_gas_wei": "integer",
    "l1_blob_base_fee_wei": "integer",
    "l1_blob_gas_used": "integer",
    "eth_usd_close": "number",
    "issuance_eth": "number",
    "registry_version": "string",
}

V1_REQUIRED_COLUMNS = ("date_utc", "rollup_id", "l2_fees_eth", "rent_paid_eth")
V1_OPTIONAL_COLUMNS = ("profit_eth", "txcount")

DECOMP_REQUIRED_COLUMNS = (
    "date_utc",
    "rollup_id",
    "rent_base_fee_burn_eth",
    "rent_blob_fee_burn_eth",
    "rent_priority_fee_eth",
    "rollup_blob_gas_used",
)
DECOMP_OPTIONAL_COLUMNS = ("rent_blob_fee_burn_wei",)

L1_REGIME_REQUIRED_COLUMNS = ("date_utc", "l1_base_fee_per_gas_wei")
L1_REGIME_OPTIONAL_COLUMNS = ("l1_blob_base_fee_wei", "l1_blob_gas_used")

PRICES_REQUIRED_COLUMNS = ("date_utc", "eth_usd_close")
ISSUANCE_REQUIRED_COLUMNS = ("date_utc", "issuance_eth")


@dataclass(frozen=True)
class SchemaField:
    name: str
    type_name: str
    nullable: bool


@dataclass(frozen=True)
class JoinTable:
    path: Path
    key_mode: str  # "date" | "date_rollup"
    rows: dict[object, dict[str, str]]

    def lookup(self, *, date_utc: str, rollup_id: str) -> dict[str, str] | None:
        if self.key_mode == "date":
            return self.rows.get(date_utc)
        return self.rows.get((date_utc, rollup_id))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _unquote_yaml_scalar(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        return v[1:-1]
    return v


def _parse_yaml_fields(schema_path: Path) -> list[SchemaField]:
    if not schema_path.exists():
        raise SystemExit(f"schema not found: {schema_path}")

    lines = schema_path.read_text(encoding="utf-8").splitlines()
    in_fields = False
    current_name: str | None = None
    current_type: str | None = None
    current_nullable: bool | None = None
    out: list[SchemaField] = []
    seen: set[str] = set()

    def flush_current() -> None:
        nonlocal current_name, current_type, current_nullable
        if current_name is None:
            return
        if current_type is None or current_nullable is None:
            raise SystemExit(
                f"schema field {current_name!r} missing type/nullable in {schema_path} "
                "(expected `type:` and `nullable:` for each field)"
            )
        if current_name in seen:
            raise SystemExit(f"schema has duplicate field name {current_name!r}: {schema_path}")
        seen.add(current_name)
        out.append(SchemaField(name=current_name, type_name=current_type, nullable=current_nullable))
        current_name = None
        current_type = None
        current_nullable = None

    for raw_line in lines:
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        if not in_fields:
            if line.strip() == "fields:":
                in_fields = True
            continue

        if not line.startswith(" ") and re.match(r"^[A-Za-z0-9_-]+\s*:", line.strip()):
            flush_current()
            break

        m_name = re.match(r"^\s*-\s*name:\s*(.+?)\s*$", line)
        if m_name:
            flush_current()
            name = _unquote_yaml_scalar(m_name.group(1))
            if name == "":
                raise SystemExit(f"schema has empty field name: {schema_path}")
            current_name = name
            continue

        m_type = re.match(r"^\s*type:\s*([A-Za-z_][A-Za-z0-9_-]*)\s*$", line)
        if m_type and current_name is not None:
            current_type = m_type.group(1).strip().lower()
            continue

        m_nullable = re.match(r"^\s*nullable:\s*(true|false)\s*$", line, flags=re.IGNORECASE)
        if m_nullable and current_name is not None:
            current_nullable = m_nullable.group(1).lower() == "true"
            continue

    flush_current()
    if not out:
        raise SystemExit(f"schema has no fields section entries: {schema_path}")
    return out


def _assert_contract_v2(schema_path: Path) -> tuple[list[str], dict[str, str], dict[str, bool]]:
    schema_fields = _parse_yaml_fields(schema_path)
    field_names = [f.name for f in schema_fields]
    field_types = {f.name: f.type_name for f in schema_fields}
    field_nullable = {f.name: f.nullable for f in schema_fields}

    if tuple(field_names) != EXPECTED_V2_FIELDS:
        raise SystemExit(
            "Contract v2 mismatch: schema field order differs from builder output.\n"
            f"- schema_path: {schema_path}\n"
            f"- schema_fields: {field_names}\n"
            f"- expected_fields: {list(EXPECTED_V2_FIELDS)}"
        )

    schema_required = tuple([name for name in field_names if not field_nullable[name]])
    if schema_required != EXPECTED_V2_REQUIRED_FIELDS:
        raise SystemExit(
            "Contract v2 mismatch: schema required fields differ from builder expectations.\n"
            f"- schema_path: {schema_path}\n"
            f"- schema_required_fields: {list(schema_required)}\n"
            f"- expected_required_fields: {list(EXPECTED_V2_REQUIRED_FIELDS)}"
        )

    for name in field_names:
        expected_type = EXPECTED_V2_TYPES.get(name)
        got_type = field_types.get(name)
        if expected_type != got_type:
            raise SystemExit(
                "Contract v2 mismatch: schema field type differs from builder expectations.\n"
                f"- field: {name}\n"
                f"- schema_type: {got_type}\n"
                f"- expected_type: {expected_type}\n"
                f"- schema_path: {schema_path}"
            )
    return field_names, field_types, field_nullable


def _parse_date(value: str, *, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {label} (expected YYYY-MM-DD): {value!r}") from exc


def _parse_int(value: str, *, label: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid integer in {label}: {value!r}") from exc


def _parse_decimal(value: str, *, label: str) -> Decimal:
    try:
        d = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise SystemExit(f"Invalid number in {label}: {value!r}") from exc
    if not d.is_finite():
        raise SystemExit(f"Non-finite number in {label}: {value!r}")
    return d


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")


def _load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise SystemExit(f"input CSV not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit(f"input CSV missing header row: {path}")
        rows = [dict(r) for r in reader]
    return list(reader.fieldnames), rows


def _require_columns(*, header: list[str], required: tuple[str, ...], label: str, path: Path) -> None:
    missing = sorted(set(required) - set(header))
    if missing:
        raise SystemExit(f"{label} missing required columns: {missing} ({path})")


def _coerce_field_value(*, field_name: str, raw_value: str, field_types: dict[str, str], row_label: str) -> str:
    value = raw_value.strip()
    if value == "":
        return ""
    t = field_types.get(field_name)
    if t is None:
        raise SystemExit(f"Unknown schema field for coercion: {field_name!r}")
    if t == "date":
        return _parse_date(value, label=f"{row_label}.{field_name}").isoformat()
    if t == "integer":
        return str(_parse_int(value, label=f"{row_label}.{field_name}"))
    if t == "number":
        return _format_decimal(_parse_decimal(value, label=f"{row_label}.{field_name}"))
    if t == "string":
        return value
    raise SystemExit(f"Unsupported schema type {t!r} for field {field_name!r}")


def _validate_output_rows(
    *,
    rows: list[dict[str, str]],
    field_names: list[str],
    field_types: dict[str, str],
    field_nullable: dict[str, bool],
) -> None:
    for idx, row in enumerate(rows, start=2):
        for field_name in field_names:
            raw = (row.get(field_name) or "").strip()
            if raw == "":
                if not field_nullable[field_name]:
                    raise SystemExit(f"Output row {idx}: required non-null field is empty: {field_name!r}")
                continue
            _coerce_field_value(
                field_name=field_name,
                raw_value=raw,
                field_types=field_types,
                row_label=f"output_row_{idx}",
            )


def _load_base_panel(
    *,
    path: Path,
    field_types: dict[str, str],
) -> dict[tuple[str, str], dict[str, str]]:
    header, rows = _load_csv_rows(path)
    _require_columns(header=header, required=V1_REQUIRED_COLUMNS, label="v1 panel", path=path)

    out: dict[tuple[str, str], dict[str, str]] = {}
    for i, row in enumerate(rows, start=2):
        d_raw = (row.get("date_utc") or "").strip()
        rid_raw = (row.get("rollup_id") or "").strip()
        if d_raw == "" or rid_raw == "":
            raise SystemExit(f"v1 panel row {i}: missing date_utc/rollup_id ({path})")
        d_norm = _parse_date(d_raw, label=f"v1 panel row {i} date_utc").isoformat()
        key = (d_norm, rid_raw)
        if key in out:
            raise SystemExit(f"v1 panel row {i}: duplicate key (date_utc, rollup_id)={key} ({path})")

        fees_raw = (row.get("l2_fees_eth") or "").strip()
        rent_raw = (row.get("rent_paid_eth") or "").strip()
        if fees_raw == "" or rent_raw == "":
            raise SystemExit(
                f"v1 panel row {i}: missing core fields l2_fees_eth/rent_paid_eth; "
                "row-inclusion rule requires both"
            )

        out[key] = {
            "date_utc": d_norm,
            "rollup_id": rid_raw,
            "l2_fees_eth": _coerce_field_value(
                field_name="l2_fees_eth",
                raw_value=fees_raw,
                field_types=field_types,
                row_label=f"v1_panel_row_{i}",
            ),
            "rent_paid_eth": _coerce_field_value(
                field_name="rent_paid_eth",
                raw_value=rent_raw,
                field_types=field_types,
                row_label=f"v1_panel_row_{i}",
            ),
            "profit_eth": "",
            "txcount": "",
        }

        if "profit_eth" in header:
            p_raw = (row.get("profit_eth") or "").strip()
            if p_raw != "":
                out[key]["profit_eth"] = _coerce_field_value(
                    field_name="profit_eth",
                    raw_value=p_raw,
                    field_types=field_types,
                    row_label=f"v1_panel_row_{i}",
                )

        if "txcount" in header:
            t_raw = (row.get("txcount") or "").strip()
            if t_raw != "":
                out[key]["txcount"] = _coerce_field_value(
                    field_name="txcount",
                    raw_value=t_raw,
                    field_types=field_types,
                    row_label=f"v1_panel_row_{i}",
                )
    return out


def _load_join_table(
    *,
    path: Path,
    dataset_label: str,
    required_columns: tuple[str, ...],
    optional_columns: tuple[str, ...],
    require_rollup_key: bool,
    field_types: dict[str, str],
) -> JoinTable:
    header, rows = _load_csv_rows(path)
    _require_columns(header=header, required=required_columns, label=dataset_label, path=path)

    header_set = set(header)
    has_rollup_key = "rollup_id" in header_set
    if require_rollup_key and not has_rollup_key:
        raise SystemExit(f"{dataset_label} must contain rollup_id key column ({path})")

    key_mode = "date_rollup" if has_rollup_key else "date"
    value_columns = [c for c in (*required_columns, *optional_columns) if c not in {"date_utc", "rollup_id"}]

    out: dict[object, dict[str, str]] = {}
    for i, row in enumerate(rows, start=2):
        d_raw = (row.get("date_utc") or "").strip()
        if d_raw == "":
            raise SystemExit(f"{dataset_label} row {i}: missing date_utc ({path})")
        d_norm = _parse_date(d_raw, label=f"{dataset_label} row {i} date_utc").isoformat()

        if key_mode == "date_rollup":
            rid_raw = (row.get("rollup_id") or "").strip()
            if rid_raw == "":
                raise SystemExit(f"{dataset_label} row {i}: missing rollup_id ({path})")
            key: object = (d_norm, rid_raw)
        else:
            key = d_norm

        if key in out:
            raise SystemExit(f"{dataset_label} row {i}: duplicate key {key!r} ({path})")

        values: dict[str, str] = {}
        for col in value_columns:
            if col not in header_set:
                continue
            raw = (row.get(col) or "").strip()
            if raw == "":
                values[col] = ""
            else:
                values[col] = _coerce_field_value(
                    field_name=col,
                    raw_value=raw,
                    field_types=field_types,
                    row_label=f"{dataset_label}_row_{i}",
                )
        out[key] = values

    return JoinTable(path=path, key_mode=key_mode, rows=out)


def _apply_join(
    *,
    output_rows: dict[tuple[str, str], dict[str, str]],
    join_table: JoinTable,
    fields: tuple[str, ...],
    join_label: str,
) -> None:
    for key, row in output_rows.items():
        d, rid = key
        matched = join_table.lookup(date_utc=d, rollup_id=rid)
        if matched is None:
            continue
        for field_name in fields:
            if field_name not in matched:
                continue
            new_value = (matched.get(field_name) or "").strip()
            if new_value == "":
                continue
            old_value = (row.get(field_name) or "").strip()
            if old_value != "" and old_value != new_value:
                raise SystemExit(
                    f"Conflicting values for {field_name!r} at key {(d, rid)} during {join_label}. "
                    f"existing={old_value!r} incoming={new_value!r}"
                )
            row[field_name] = new_value


def _write_csv(path: Path, *, field_names: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=field_names, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in field_names})


def build_panel_v2(
    *,
    panel_v1_csv: Path,
    schema_path: Path,
    out_csv: Path,
    decomposition_csv: Path | None,
    l1_regime_csv: Path | None,
    prices_csv: Path | None,
    issuance_csv: Path | None,
    registry_version: str | None,
) -> dict[str, object]:
    field_names, field_types, field_nullable = _assert_contract_v2(schema_path)
    base_map = _load_base_panel(path=panel_v1_csv, field_types=field_types)

    output_rows: dict[tuple[str, str], dict[str, str]] = {}
    for key, base in base_map.items():
        row = {field: "" for field in field_names}
        row["date_utc"] = base["date_utc"]
        row["rollup_id"] = base["rollup_id"]
        row["l2_fees_eth"] = base["l2_fees_eth"]
        row["rent_paid_eth"] = base["rent_paid_eth"]
        row["profit_eth"] = base["profit_eth"]
        row["txcount"] = base["txcount"]
        if registry_version is not None and registry_version.strip() != "":
            row["registry_version"] = registry_version.strip()
        output_rows[key] = row

    join_meta: dict[str, object] = {}

    if decomposition_csv is not None:
        decomp = _load_join_table(
            path=decomposition_csv,
            dataset_label="decomposition_csv",
            required_columns=DECOMP_REQUIRED_COLUMNS,
            optional_columns=DECOMP_OPTIONAL_COLUMNS,
            require_rollup_key=True,
            field_types=field_types,
        )
        _apply_join(
            output_rows=output_rows,
            join_table=decomp,
            fields=(
                "rent_base_fee_burn_eth",
                "rent_blob_fee_burn_eth",
                "rent_priority_fee_eth",
                "rent_blob_fee_burn_wei",
                "rollup_blob_gas_used",
            ),
            join_label="decomposition join",
        )
        join_meta["decomposition_rows"] = len(decomp.rows)

    if l1_regime_csv is not None:
        regime = _load_join_table(
            path=l1_regime_csv,
            dataset_label="l1_regime_csv",
            required_columns=L1_REGIME_REQUIRED_COLUMNS,
            optional_columns=L1_REGIME_OPTIONAL_COLUMNS,
            require_rollup_key=False,
            field_types=field_types,
        )
        _apply_join(
            output_rows=output_rows,
            join_table=regime,
            fields=("l1_base_fee_per_gas_wei", "l1_blob_base_fee_wei", "l1_blob_gas_used"),
            join_label="l1 regime join",
        )
        join_meta["l1_regime_rows"] = len(regime.rows)
        join_meta["l1_regime_key_mode"] = regime.key_mode

    if prices_csv is not None:
        prices = _load_join_table(
            path=prices_csv,
            dataset_label="prices_csv",
            required_columns=PRICES_REQUIRED_COLUMNS,
            optional_columns=(),
            require_rollup_key=False,
            field_types=field_types,
        )
        _apply_join(
            output_rows=output_rows,
            join_table=prices,
            fields=("eth_usd_close",),
            join_label="prices join",
        )
        join_meta["prices_rows"] = len(prices.rows)
        join_meta["prices_key_mode"] = prices.key_mode

    if issuance_csv is not None:
        issuance = _load_join_table(
            path=issuance_csv,
            dataset_label="issuance_csv",
            required_columns=ISSUANCE_REQUIRED_COLUMNS,
            optional_columns=(),
            require_rollup_key=False,
            field_types=field_types,
        )
        _apply_join(
            output_rows=output_rows,
            join_table=issuance,
            fields=("issuance_eth",),
            join_label="issuance join",
        )
        join_meta["issuance_rows"] = len(issuance.rows)
        join_meta["issuance_key_mode"] = issuance.key_mode

    sorted_rows = [output_rows[k] for k in sorted(output_rows.keys())]
    _validate_output_rows(
        rows=sorted_rows,
        field_names=field_names,
        field_types=field_types,
        field_nullable=field_nullable,
    )
    _write_csv(out_csv, field_names=field_names, rows=sorted_rows)

    return {
        "ok": True,
        "out_csv": str(out_csv),
        "row_count": len(sorted_rows),
        "joins": join_meta,
        "schema_contract": {
            "schema_path": str(schema_path),
            "field_count": len(field_names),
            "required_field_count": len([f for f in field_names if not field_nullable[f]]),
        },
    }


def main(argv: list[str]) -> None:
    root = _repo_root()

    parser = argparse.ArgumentParser(prog="panel_build_daily_rollup_panel_v2.py")
    parser.add_argument("--sample", action="store_true", help="Use committed sample assets for deterministic sample mode.")
    parser.add_argument("--schema", default="contracts/schemas/panel_schema_str_v2.yaml", help="Path to v2 schema YAML.")
    parser.add_argument(
        "--panel-v1-csv",
        default=None,
        help="Base v1 panel CSV (required fields: date_utc, rollup_id, l2_fees_eth, rent_paid_eth).",
    )
    parser.add_argument("--decomposition-csv", default=None, help="Optional decomposition CSV keyed by date_utc, rollup_id.")
    parser.add_argument(
        "--l1-regime-csv",
        default=None,
        help="Optional L1 regime CSV keyed by date_utc or date_utc, rollup_id (must include l1_base_fee_per_gas_wei).",
    )
    parser.add_argument("--prices-csv", default=None, help="Optional prices CSV keyed by date_utc (or date_utc, rollup_id).")
    parser.add_argument("--issuance-csv", default=None, help="Optional issuance CSV keyed by date_utc (or date_utc, rollup_id).")
    parser.add_argument("--registry-version", default=None, help="Optional value for registry_version output field.")
    parser.add_argument("--out", dest="out_csv", default=None, help="Output CSV path.")
    args = parser.parse_args(argv[1:])

    schema_path = Path(args.schema)
    if not schema_path.is_absolute():
        schema_path = root / schema_path

    if args.sample:
        panel_v1_csv = Path(args.panel_v1_csv) if args.panel_v1_csv else (root / "data/samples/panels/daily_rollup_panel_v1_sample.csv")
        sample_enrichment = root / "data/samples/panels/daily_rollup_panel_v2_sample.csv"
        decomposition_csv = Path(args.decomposition_csv) if args.decomposition_csv else sample_enrichment
        l1_regime_csv = Path(args.l1_regime_csv) if args.l1_regime_csv else sample_enrichment
        prices_csv = Path(args.prices_csv) if args.prices_csv else sample_enrichment
        issuance_csv = Path(args.issuance_csv) if args.issuance_csv else sample_enrichment
        out_csv = Path(args.out_csv) if args.out_csv else (root / "data/processed/panels/daily_rollup_panel_v2_sample.csv")
    else:
        panel_v1_csv = (
            Path(args.panel_v1_csv)
            if args.panel_v1_csv
            else (root / "data/processed/panels/daily_rollup_panel_v1.csv")
        )
        decomposition_csv = Path(args.decomposition_csv) if args.decomposition_csv else None
        l1_regime_csv = Path(args.l1_regime_csv) if args.l1_regime_csv else None
        prices_csv = Path(args.prices_csv) if args.prices_csv else None
        issuance_csv = Path(args.issuance_csv) if args.issuance_csv else None
        out_csv = Path(args.out_csv) if args.out_csv else (root / "data/processed/panels/daily_rollup_panel_v2.csv")

    def _abs_if_not_none(p: Path | None) -> Path | None:
        if p is None:
            return None
        return p if p.is_absolute() else (root / p)

    result = build_panel_v2(
        panel_v1_csv=_abs_if_not_none(panel_v1_csv) or panel_v1_csv,
        schema_path=_abs_if_not_none(schema_path) or schema_path,
        out_csv=_abs_if_not_none(out_csv) or out_csv,
        decomposition_csv=_abs_if_not_none(decomposition_csv),
        l1_regime_csv=_abs_if_not_none(l1_regime_csv),
        prices_csv=_abs_if_not_none(prices_csv),
        issuance_csv=_abs_if_not_none(issuance_csv),
        registry_version=args.registry_version,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv)
