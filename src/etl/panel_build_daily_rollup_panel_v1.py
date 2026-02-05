from __future__ import annotations

"""Build the contract v1 daily rollup panel (minimum STR panel).

Inputs (default):
- `registry/rollup_registry_v1.csv`
- `data/samples/panels/daily_rollup_panel_v1_sample.csv` (when `--sample`)

Outputs (default):
- `data/processed/panels/daily_rollup_panel_v1.csv` (full mode)
- `data/processed/panels/daily_rollup_panel_v1_sample.csv` (sample mode)
- Optional processed manifest under `data/processed_manifest/` (when `--write-manifest`)

How to run:
- Sample build + manifest:
  `python src/etl/panel_build_daily_rollup_panel_v1.py --sample --write-manifest --as-of 2026-02-04`
- Full build (provide an input candidate panel CSV):
  `python src/etl/panel_build_daily_rollup_panel_v1.py --input data/processed/<source>/candidate.csv --out data/processed/panels/daily_rollup_panel_v1.csv`
"""

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


PANEL_REQUIRED_COLUMNS = ("date_utc", "rollup_id", "l2_fees_eth", "rent_paid_eth")
PANEL_OPTIONAL_COLUMNS = ("profit_eth", "txcount")
PANEL_OUTPUT_COLUMNS = PANEL_REQUIRED_COLUMNS + PANEL_OPTIONAL_COLUMNS


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_within_repo(root: Path, target: Path) -> Path:
    try:
        return target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"path must be inside repo root: {root} (got {target})") from exc


def _parse_bool(value: str) -> bool:
    v = value.strip().lower()
    if v in {"true", "1", "yes", "y"}:
        return True
    if v in {"false", "0", "no", "n", ""}:
        return False
    raise SystemExit(f"Invalid boolean value: {value!r}")


def _parse_date(value: str, *, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {label} date (expected YYYY-MM-DD): {value!r}") from exc


def _parse_optional_date(value: str) -> date | None:
    v = value.strip()
    if v == "":
        return None
    return _parse_date(v, label="registry")


def _parse_decimal(value: str, *, label: str) -> Decimal:
    try:
        d = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise SystemExit(f"Invalid decimal in {label}: {value!r}") from exc
    if not d.is_finite():
        raise SystemExit(f"Non-finite decimal in {label}: {value!r}")
    return d


def _format_decimal(value: Decimal) -> str:
    # Avoid scientific notation in CSV.
    return format(value, "f")


def _unquote_yaml_scalar(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        return v[1:-1]
    return v


def _load_schema_fields(schema_path: Path) -> tuple[tuple[str, ...], dict[str, bool]]:
    """Parse a minimal subset of the YAML panel schema (stdlib-only).

    We intentionally avoid a YAML dependency at bootstrap. This loader only
    supports the simple structure used in `contracts/schemas/panel_schema_str_v1.yaml`:

      fields:
        - name: foo
          nullable: false
        - name: bar
          nullable: true
    """
    if not schema_path.exists():
        raise SystemExit(f"schema not found: {schema_path}")

    text = schema_path.read_text(encoding="utf-8")
    fields: list[str] = []
    seen: set[str] = set()
    nullable: dict[str, bool] = {}
    in_fields = False
    current_field: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        if not in_fields:
            if line.strip() == "fields:":
                in_fields = True
            continue

        # Stop if we hit a new top-level key.
        if not line.startswith(" ") and re.match(r"^[A-Za-z0-9_-]+\s*:", line.strip()):
            break

        m_name = re.match(r"^\s*-\s*name:\s*(.+?)\s*$", line)
        if m_name:
            name = _unquote_yaml_scalar(m_name.group(1))
            if name == "":
                raise SystemExit(f"schema field name is empty: {schema_path}")
            if name in seen:
                raise SystemExit(f"schema has duplicate field name {name!r}: {schema_path}")
            seen.add(name)
            fields.append(name)
            current_field = name
            continue

        m_nullable = re.match(r"^\s*nullable:\s*(true|false)\s*$", line.strip(), flags=re.IGNORECASE)
        if m_nullable and current_field is not None:
            nullable[current_field] = m_nullable.group(1).lower() == "true"

    if not fields:
        raise SystemExit(f"schema has no fields (expected fields: ...): {schema_path}")
    missing_nullable = [f for f in fields if f not in nullable]
    if missing_nullable:
        raise SystemExit(f"schema fields missing `nullable` flag: {missing_nullable} ({schema_path})")

    return tuple(fields), nullable


def _assert_contract_v1(*, schema_path: Path) -> dict[str, object]:
    """Fail fast if the locked contract v1 schema drifts."""
    schema_fields, schema_nullable = _load_schema_fields(schema_path)

    if schema_fields != PANEL_OUTPUT_COLUMNS:
        raise SystemExit(
            "Contract v1 mismatch: schema field order differs from builder output.\n"
            f"- schema_path: {schema_path}\n"
            f"- schema_fields: {list(schema_fields)}\n"
            f"- expected_fields: {list(PANEL_OUTPUT_COLUMNS)}\n"
            "Update the builder to match the locked schema, or update the schema with a W0 decision."
        )

    required_from_schema = tuple([f for f in schema_fields if not schema_nullable[f]])
    if required_from_schema != PANEL_REQUIRED_COLUMNS:
        raise SystemExit(
            "Contract v1 mismatch: schema required fields differ from builder expectations.\n"
            f"- schema_path: {schema_path}\n"
            f"- schema_required_fields: {list(required_from_schema)}\n"
            f"- expected_required_fields: {list(PANEL_REQUIRED_COLUMNS)}\n"
        )

    core = ("l2_fees_eth", "rent_paid_eth")
    missing_core = [c for c in core if c not in required_from_schema]
    if missing_core:
        raise SystemExit(f"Contract v1 mismatch: core fields must be non-nullable in schema: {missing_core} ({schema_path})")

    return {
        "schema_fields": list(schema_fields),
        "schema_required_fields": list(required_from_schema),
    }


@dataclass(frozen=True)
class RegistryRow:
    rollup_id: str
    in_scope: bool
    status: str
    start_date_utc: date | None
    end_date_utc: date | None

    def includes(self, d: date) -> bool:
        if self.status == "deprecated":
            return False
        if not self.in_scope:
            return False
        if self.start_date_utc is not None and d < self.start_date_utc:
            return False
        if self.end_date_utc is not None and d > self.end_date_utc:
            return False
        if self.status == "inactive" and self.end_date_utc is None:
            raise SystemExit(f"Registry row {self.rollup_id!r} has status=inactive but missing end_date_utc")
        return True


def load_registry(path: Path) -> dict[str, RegistryRow]:
    if not path.exists():
        raise SystemExit(f"registry not found: {path}")

    rows: dict[str, RegistryRow] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"rollup_id", "in_scope", "status", "start_date_utc", "end_date_utc"}
        if reader.fieldnames is None:
            raise SystemExit("registry CSV missing header row")
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise SystemExit(f"registry CSV missing required columns: {missing}")

        for i, r in enumerate(reader, start=2):
            rollup_id = (r.get("rollup_id") or "").strip()
            if rollup_id == "":
                raise SystemExit(f"registry row {i}: missing rollup_id")
            if rollup_id in rows:
                raise SystemExit(f"registry row {i}: duplicate rollup_id: {rollup_id!r}")

            in_scope = _parse_bool(r.get("in_scope", ""))
            status = (r.get("status") or "").strip().lower() or "active"
            start = _parse_optional_date(r.get("start_date_utc", ""))
            end = _parse_optional_date(r.get("end_date_utc", ""))

            rows[rollup_id] = RegistryRow(
                rollup_id=rollup_id,
                in_scope=in_scope,
                status=status,
                start_date_utc=start,
                end_date_utc=end,
            )
    if len(rows) == 0:
        raise SystemExit(
            f"registry is empty (no rollup rows): {path}. Seed `registry/rollup_registry_v1.csv` (see `registry/README.md`)."
        )
    return rows


def _validate_input_columns(header: list[str]) -> None:
    got = set(header)
    missing = [c for c in PANEL_REQUIRED_COLUMNS if c not in got]
    if missing:
        raise SystemExit(f"Input is missing required columns: {missing}")


def build_panel(*, registry: dict[str, RegistryRow], input_csv: Path) -> tuple[list[dict[str, object]], dict[str, int]]:
    if not input_csv.exists():
        raise SystemExit(f"input not found: {input_csv}")

    counts = {
        "input_rows": 0,
        "output_rows": 0,
        "dropped_missing_core": 0,
        "dropped_out_of_scope": 0,
        "dropped_outside_window": 0,
        "dropped_deprecated": 0,
    }

    out_rows: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str]] = set()

    with input_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit("Input CSV missing header row")
        _validate_input_columns(reader.fieldnames)

        for i, r in enumerate(reader, start=2):
            counts["input_rows"] += 1
            raw_date = (r.get("date_utc") or "").strip()
            raw_rollup_id = (r.get("rollup_id") or "").strip()
            if raw_date == "" or raw_rollup_id == "":
                raise SystemExit(f"input row {i}: missing date_utc or rollup_id")

            d = _parse_date(raw_date, label="date_utc")
            if raw_rollup_id not in registry:
                raise SystemExit(f"input row {i}: unknown rollup_id (not in registry): {raw_rollup_id!r}")
            reg = registry[raw_rollup_id]

            try:
                included = reg.includes(d)
            except SystemExit:
                raise

            if not reg.in_scope:
                counts["dropped_out_of_scope"] += 1
                continue
            if reg.status == "deprecated":
                counts["dropped_deprecated"] += 1
                continue
            if not included:
                counts["dropped_outside_window"] += 1
                continue

            raw_fees = (r.get("l2_fees_eth") or "").strip()
            raw_rent = (r.get("rent_paid_eth") or "").strip()
            if raw_fees == "" or raw_rent == "":
                counts["dropped_missing_core"] += 1
                continue

            fees = _parse_decimal(raw_fees, label="l2_fees_eth")
            rent = _parse_decimal(raw_rent, label="rent_paid_eth")
            if fees < 0 or rent < 0:
                raise SystemExit(f"input row {i}: negative values not allowed (fees={fees}, rent={rent})")

            key = (d.isoformat(), raw_rollup_id)
            if key in seen_keys:
                raise SystemExit(f"input row {i}: duplicate (date_utc, rollup_id): {key}")
            seen_keys.add(key)

            out: dict[str, object] = {
                "date_utc": d.isoformat(),
                "rollup_id": raw_rollup_id,
                "l2_fees_eth": _format_decimal(fees),
                "rent_paid_eth": _format_decimal(rent),
                "profit_eth": "",
                "txcount": "",
            }

            raw_profit = (r.get("profit_eth") or "").strip()
            if raw_profit != "":
                out["profit_eth"] = _format_decimal(_parse_decimal(raw_profit, label="profit_eth"))
            raw_txcount = (r.get("txcount") or "").strip()
            if raw_txcount != "":
                try:
                    txcount = int(raw_txcount)
                except ValueError as exc:
                    raise SystemExit(f"input row {i}: invalid txcount: {raw_txcount!r}") from exc
                if txcount < 0:
                    raise SystemExit(f"input row {i}: negative txcount not allowed: {txcount}")
                out["txcount"] = str(txcount)

            out_rows.append(out)

    out_rows.sort(key=lambda r: (str(r["date_utc"]), str(r["rollup_id"])))
    counts["output_rows"] = len(out_rows)
    return out_rows, counts


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(PANEL_OUTPUT_COLUMNS), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in PANEL_OUTPUT_COLUMNS})


def _manifest_default_name(*, sample: bool) -> str:
    return "daily_rollup_panel_v1_sample" if sample else "daily_rollup_panel_v1"


def _command_tokens_for_manifest(root: Path) -> list[str]:
    argv0 = Path(sys.argv[0])
    try:
        argv0_rel = _ensure_within_repo(root, argv0.resolve())
        script_token = str(argv0_rel)
    except SystemExit:
        script_token = sys.argv[0]
    return ["python", script_token, *sys.argv[1:]]


def _write_processed_manifest(
    *,
    name: str,
    as_of: date,
    manifest_out: Path | None,
    manifest_inputs: list[Path],
    outputs: list[Path],
    meta: dict[str, object],
) -> None:
    root = _repo_root()
    helper = root / "scripts/make_processed_manifest.py"
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
            *[str(_ensure_within_repo(root, p.resolve())) for p in manifest_inputs],
            "--outputs",
            *[str(_ensure_within_repo(root, p.resolve())) for p in outputs],
            "--meta-json",
            str(meta_path),
        ]
        if manifest_out is not None:
            cmd.extend(["--out", str(_ensure_within_repo(root, manifest_out.resolve()))])
        cmd.extend(["--", *_command_tokens_for_manifest(root)])
        subprocess.run(cmd, cwd=root, check=True)
    finally:
        try:
            meta_path.unlink()
        except OSError:
            pass


def main(argv: list[str]) -> None:
    root = _repo_root()

    p = argparse.ArgumentParser(prog="panel_build_daily_rollup_panel_v1.py")
    p.add_argument("--sample", action="store_true", help="Use the committed sample input panel")
    p.add_argument("--registry", default="registry/rollup_registry_v1.csv")
    p.add_argument("--schema", default="contracts/schemas/panel_schema_str_v1.yaml")
    p.add_argument("--input", dest="input_csv", default=None, help="Input candidate panel CSV")
    p.add_argument("--out", dest="out_csv", default=None, help="Output CSV path (contract v1)")

    p.add_argument("--write-manifest", action="store_true", help="Write a processed manifest via scripts/make_processed_manifest.py")
    p.add_argument("--as-of", dest="as_of", default=None, help="Manifest as-of date (YYYY-MM-DD, UTC)")
    p.add_argument("--manifest-name", dest="manifest_name", default=None)
    p.add_argument("--manifest-out", dest="manifest_out", default=None, help="Optional output path for manifest JSON")
    p.add_argument("--manifest-inputs", nargs="*", default=[], help="Additional inputs to include in the manifest")
    args = p.parse_args(argv[1:])

    registry_path = Path(args.registry)
    schema_path = Path(args.schema)
    schema_abs = schema_path if schema_path.is_absolute() else (root / schema_path)
    contract_meta = _assert_contract_v1(schema_path=schema_abs)

    if args.sample:
        input_csv = root / "data/samples/panels/daily_rollup_panel_v1_sample.csv"
        out_csv = root / "data/processed/panels/daily_rollup_panel_v1_sample.csv"
    else:
        if args.input_csv is None:
            raise SystemExit("Missing --input (or use --sample)")
        input_csv = Path(args.input_csv)
        out_csv = Path(args.out_csv) if args.out_csv else (root / "data/processed/panels/daily_rollup_panel_v1.csv")

    registry = load_registry(registry_path if registry_path.is_absolute() else (root / registry_path))
    rows, counts = build_panel(registry=registry, input_csv=input_csv if input_csv.is_absolute() else (root / input_csv))
    _write_csv(out_csv if out_csv.is_absolute() else (root / out_csv), rows)

    if args.write_manifest:
        if args.as_of is None:
            raise SystemExit("Missing --as-of (required with --write-manifest)")
        as_of = _parse_date(args.as_of, label="as_of")

        manifest_name = args.manifest_name or _manifest_default_name(sample=args.sample)
        manifest_out = Path(args.manifest_out) if args.manifest_out else None

        manifest_inputs: list[Path] = []
        manifest_inputs.append(registry_path if registry_path.is_absolute() else (root / registry_path))
        manifest_inputs.append(schema_path if schema_path.is_absolute() else (root / schema_path))
        manifest_inputs.append(input_csv if input_csv.is_absolute() else (root / input_csv))
        for extra in args.manifest_inputs:
            pth = Path(extra)
            manifest_inputs.append(pth if pth.is_absolute() else (root / pth))

        out_abs = out_csv if out_csv.is_absolute() else (root / out_csv)
        output_rollups = sorted({str(r["rollup_id"]) for r in rows})
        output_dates = sorted({str(r["date_utc"]) for r in rows})
        meta = {
            "panel_schema_version": 1,
            "schema_path": str(_ensure_within_repo(root, (schema_path if schema_path.is_absolute() else (root / schema_path)).resolve())),
            "schema_sha256": _sha256_file((schema_path if schema_path.is_absolute() else (root / schema_path)).resolve()),
            "registry_path": str(_ensure_within_repo(root, (registry_path if registry_path.is_absolute() else (root / registry_path)).resolve())),
            "registry_sha256": _sha256_file((registry_path if registry_path.is_absolute() else (root / registry_path)).resolve()),
            "contract_assertions": contract_meta,
            "universe": {
                "registry_in_scope_rollups": sorted([k for k, v in registry.items() if v.in_scope and v.status != "deprecated"]),
                "panel_rollups_in_output": output_rollups,
                "panel_date_min": (min(output_dates) if output_dates else None),
                "panel_date_max": (max(output_dates) if output_dates else None),
                "registry_filter_rules": {
                    "in_scope_required": True,
                    "excluded_statuses": ["deprecated"],
                    "window_rule": "start_date_utc <= date_utc <= end_date_utc (when set); inactive requires end_date_utc",
                    "row_inclusion_rule": "emit row iff l2_fees_eth and rent_paid_eth present (missingness encoded by row omission, not nulls)",
                },
            },
            "counts": counts,
        }

        _write_processed_manifest(
            name=manifest_name,
            as_of=as_of,
            manifest_out=manifest_out,
            manifest_inputs=manifest_inputs,
            outputs=[out_abs],
            meta=meta,
        )

    print(json.dumps({"ok": True, "counts": counts, "out_csv": str(out_csv)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv)
