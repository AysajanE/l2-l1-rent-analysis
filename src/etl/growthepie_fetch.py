from __future__ import annotations

"""growthepie ETL: snapshot exports and build a normalized vendor daily rollup panel.

This is the primary data source for the STR denominator (`l2_fees_eth`) and a secondary
vendor series for rent/profit (triangulation only for rent; on-chain remains authoritative).

Raw snapshots are append-only under `data/raw/growthepie/<run-date>/...`.
Processed outputs are rebuildable under `data/processed/growthepie/...` (gitignored).

Example (snapshot + build processed CSV + write raw manifest):
  python src/etl/growthepie_fetch.py --run-date 2026-02-05 --write-raw-manifest

Example (rebuild processed CSV from an existing snapshot directory, no network):
  python src/etl/growthepie_fetch.py --from-snapshot data/raw/growthepie/2026-02-05
"""

import argparse
import csv
import json
import math
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.etl.offchain.files import ensure_dir, write_bytes_append_only, write_text_append_only  # noqa: E402
from src.etl.offchain.http import http_get_json, http_get_text  # noqa: E402


GROWTHEPIE_BASE = "https://api.growthepie.com/v1"
MASTER_URL = f"{GROWTHEPIE_BASE}/master.json"

# Export endpoints are *category* endpoints; each row in the response contains a metric_key.
EXPORT_ENDPOINTS: dict[str, str] = {
    "fees": f"{GROWTHEPIE_BASE}/export/fees.json",
    "rent_paid": f"{GROWTHEPIE_BASE}/export/rent_paid.json",
    "profit": f"{GROWTHEPIE_BASE}/export/profit.json",
    "txcount": f"{GROWTHEPIE_BASE}/export/txcount.json",
}

# Locked selection of ETH-native metric keys observed in the growthepie exports (2026-02-05).
# If growthepie changes these keys, discovery output should be updated and this script will fail fast.
METRIC_KEY_MAP: dict[str, str] = {
    "l2_fees_eth": "fees_paid_eth",
    "rent_paid_eth_vendor": "rent_paid_eth",
    "profit_eth": "profit_eth",
    "txcount": "txcount",
}

# Canonical sample conventions (see data/samples/README.md)
SAMPLE_WINDOW_START = date(2024, 2, 20)
SAMPLE_WINDOW_END = date(2024, 4, 30)
SAMPLE_ROLLUPS = ("arbitrum", "optimism", "base")

PANEL_SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "panel_schema_str_v1.yaml"
PANEL_COLUMNS = ("date_utc", "rollup_id", "l2_fees_eth", "rent_paid_eth", "profit_eth", "txcount")
PANEL_REQUIRED_COLUMNS = ("date_utc", "rollup_id", "l2_fees_eth", "rent_paid_eth")


def _repo_root() -> Path:
    return REPO_ROOT


def _parse_date(value: str, *, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {label} date (expected YYYY-MM-DD): {value!r}") from exc


def _format_date(d: date) -> str:
    return d.isoformat()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(_read_text(path))


def _write_json_pretty(path: Path, obj: Any) -> None:
    write_text_append_only(path, json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _unquote_yaml_scalar(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        return v[1:-1]
    return v


def _load_schema_fields(schema_path: Path) -> tuple[tuple[str, ...], dict[str, bool]]:
    """Parse the minimal schema shape used by contracts/schemas/panel_schema_str_v1.yaml."""
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


def _assert_panel_contract_v1(*, schema_path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Fail fast if the locked STR panel schema drifts from ETL output expectations."""
    schema_fields, schema_nullable = _load_schema_fields(schema_path)
    if schema_fields != PANEL_COLUMNS:
        raise SystemExit(
            "Schema mismatch: growthepie ETL output columns differ from locked STR schema.\n"
            f"- schema_path: {schema_path}\n"
            f"- schema_fields: {list(schema_fields)}\n"
            f"- expected_fields: {list(PANEL_COLUMNS)}\n"
        )

    required_from_schema = tuple([f for f in schema_fields if not schema_nullable[f]])
    if required_from_schema != PANEL_REQUIRED_COLUMNS:
        raise SystemExit(
            "Schema mismatch: required (non-nullable) fields differ from ETL expectations.\n"
            f"- schema_path: {schema_path}\n"
            f"- schema_required_fields: {list(required_from_schema)}\n"
            f"- expected_required_fields: {list(PANEL_REQUIRED_COLUMNS)}\n"
        )

    return schema_fields, required_from_schema


def _render_command_tokens_for_manifest(root: Path) -> list[str]:
    argv0 = Path(sys.argv[0])
    try:
        script_token = str(argv0.resolve().relative_to(root.resolve()))
    except Exception:
        script_token = sys.argv[0]
    return ["python", script_token, *sys.argv[1:]]


def _write_raw_manifest(*, source: str, snapshot_dir: Path, as_of: date) -> Path:
    root = _repo_root()
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
    out_path: Path | None = None,
) -> Path:
    root = _repo_root()
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
        ]
        if out_path is not None:
            cmd.extend(["--out", str(out_path)])
        cmd.extend(["--", *_render_command_tokens_for_manifest(root)])
        subprocess.run(cmd, cwd=root, check=True)
    finally:
        try:
            meta_path.unlink()
        except OSError:
            pass

    return out_path if out_path is not None else (root / "data" / "processed_manifest" / f"{name}_{as_of.isoformat()}.json")


@dataclass(frozen=True)
class RegistryRow:
    rollup_id: str
    origin_key: str | None
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


def _parse_bool(value: str) -> bool:
    v = (value or "").strip().lower()
    if v in {"true", "1", "yes", "y"}:
        return True
    if v in {"false", "0", "no", "n", ""}:
        return False
    raise SystemExit(f"Invalid boolean value: {value!r}")


def _parse_optional_date(value: str) -> date | None:
    s = (value or "").strip()
    if s == "":
        return None
    return _parse_date(s, label="registry")


def load_registry(path: Path) -> dict[str, RegistryRow]:
    if not path.exists():
        raise SystemExit(f"registry not found: {path}")

    out: dict[str, RegistryRow] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit("registry CSV missing header row")
        required = {"rollup_id", "origin_key", "in_scope", "status", "start_date_utc", "end_date_utc"}
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise SystemExit(f"registry CSV missing required columns: {missing}")

        for i, row in enumerate(reader, start=2):
            rollup_id = (row.get("rollup_id") or "").strip()
            if rollup_id == "":
                raise SystemExit(f"registry row {i}: missing rollup_id")
            if rollup_id in out:
                raise SystemExit(f"registry row {i}: duplicate rollup_id: {rollup_id!r}")

            origin_key = (row.get("origin_key") or "").strip() or None
            in_scope = _parse_bool(row.get("in_scope", ""))
            status = (row.get("status") or "").strip().lower() or "active"
            start = _parse_optional_date(row.get("start_date_utc", ""))
            end = _parse_optional_date(row.get("end_date_utc", ""))

            out[rollup_id] = RegistryRow(
                rollup_id=rollup_id,
                origin_key=origin_key,
                in_scope=in_scope,
                status=status,
                start_date_utc=start,
                end_date_utc=end,
            )
    if not out:
        raise SystemExit(f"registry is empty: {path}")
    return out


def _origin_key_to_rollup_id(registry: dict[str, RegistryRow]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for rid, row in registry.items():
        if row.origin_key is None:
            continue
        key = row.origin_key
        if key != rid:
            raise SystemExit(
                "registry canonical mapping violated for growthepie rows: expected rollup_id == origin_key "
                f"but saw rollup_id={rid!r}, origin_key={key!r}"
            )
        if key in mapping and mapping[key] != rid:
            raise SystemExit(f"registry has ambiguous origin_key mapping: {key!r} maps to {mapping[key]!r} and {rid!r}")
        mapping[key] = rid
    return mapping


def cmd_discover() -> int:
    master = http_get_json(MASTER_URL, timeout_seconds=30)
    metrics = master.get("metrics") if isinstance(master, dict) else None
    chains = master.get("chains") if isinstance(master, dict) else None

    out: dict[str, object] = {
        "master_url": MASTER_URL,
        "export_endpoints": EXPORT_ENDPOINTS,
        "locked_metric_key_selection": METRIC_KEY_MAP,
        "notes": [
            "Exports are category endpoints; each row includes a `metric_key` (e.g., fees_paid_eth vs fees_paid_usd).",
            "This repo uses ETH-native series for STR (fees_paid_eth, rent_paid_eth, profit_eth).",
        ],
    }
    if isinstance(metrics, dict):
        out["master_metrics"] = sorted(list(metrics.keys()))
    if isinstance(chains, dict):
        out["master_chain_keys_count"] = len(chains)

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def _snapshot_growthepie(*, run_date: date, out_dir: Path) -> list[Path]:
    ensure_dir(out_dir)
    written: list[Path] = []

    master = http_get_json(MASTER_URL, timeout_seconds=30)
    master_path = out_dir / "master.json"
    _write_json_pretty(master_path, master)
    written.append(master_path)

    export_dir = out_dir / "export"
    ensure_dir(export_dir)
    for name, url in EXPORT_ENDPOINTS.items():
        payload = http_get_text(url, timeout_seconds=60)
        path = export_dir / f"{name}.json"
        write_text_append_only(path, payload + ("\n" if not payload.endswith("\n") else ""), encoding="utf-8")
        written.append(path)

    return written


def _resolve_export_paths(snapshot_dir: Path) -> dict[str, Path]:
    """Support both the current snapshot layout and a legacy flat-file layout."""
    export_dir = snapshot_dir / "export"
    if export_dir.exists() and export_dir.is_dir():
        return {k: export_dir / f"{k}.json" for k in EXPORT_ENDPOINTS.keys()}

    # Legacy layout observed in early repo scaffolding.
    legacy = {k: snapshot_dir / f"export_{k}.json" for k in EXPORT_ENDPOINTS.keys()}
    return legacy


def _load_export_rows(path: Path) -> list[dict[str, object]]:
    data = _load_json(path)
    if not isinstance(data, list):
        raise SystemExit(f"Unexpected export shape (expected list): {path}")
    out: list[dict[str, object]] = []
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            continue
        if not isinstance(row.get("origin_key"), str) or not isinstance(row.get("date"), str) or "value" not in row:
            continue
        out.append(row)
    return out


def _coerce_float(value: object, *, label: str) -> float:
    if isinstance(value, (int, float)):
        out = float(value)
        if not math.isfinite(out):
            raise SystemExit(f"Non-finite numeric value for {label}: {value!r}")
        return out
    if isinstance(value, str):
        out = float(value)
        if not math.isfinite(out):
            raise SystemExit(f"Non-finite numeric value for {label}: {value!r}")
        return out
    raise SystemExit(f"Invalid numeric value for {label}: {value!r}")


def _assert_panel_rows(
    *,
    rows: list[dict[str, str]],
    schema_fields: tuple[str, ...],
    schema_required_fields: tuple[str, ...],
) -> None:
    expected_keys = set(schema_fields)

    for i, row in enumerate(rows):
        row_keys = set(row.keys())
        if row_keys != expected_keys:
            missing = sorted(expected_keys - row_keys)
            extra = sorted(row_keys - expected_keys)
            raise SystemExit(f"row[{i}] column mismatch: missing={missing} extra={extra}")

        for field in schema_required_fields:
            if (row.get(field) or "") == "":
                raise SystemExit(f"row[{i}] missing required field: {field}")

        _parse_date(row["date_utc"], label=f"row[{i}].date_utc")
        if row["rollup_id"].strip() == "":
            raise SystemExit(f"row[{i}] has empty rollup_id")

        for field in ["l2_fees_eth", "rent_paid_eth", "profit_eth"]:
            raw = (row.get(field) or "").strip()
            if raw == "":
                continue
            val = _coerce_float(raw, label=f"row[{i}].{field}")
            if field in {"l2_fees_eth", "rent_paid_eth"} and val < 0:
                raise SystemExit(f"row[{i}] has negative value for {field}: {val}")

        tx_raw = (row.get("txcount") or "").strip()
        if tx_raw != "":
            try:
                tx = int(tx_raw)
            except ValueError as exc:
                raise SystemExit(f"row[{i}] txcount is not an integer: {tx_raw!r}") from exc
            if tx < 0:
                raise SystemExit(f"row[{i}] has negative txcount: {tx}")


def build_vendor_panel(
    *,
    registry: dict[str, RegistryRow],
    export_paths: dict[str, Path],
    start_date: date,
    end_date: date,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    origin_to_rollup = _origin_key_to_rollup_id(registry)

    # Only include in-scope rollups (and not deprecated) per protocol; window filtering is applied per row.
    in_scope_rollups = {rid for rid, row in registry.items() if row.in_scope and row.status != "deprecated"}
    in_scope_origins = {registry[rid].origin_key for rid in in_scope_rollups if registry[rid].origin_key is not None}

    required = {"fees", "rent_paid", "profit", "txcount"}
    missing_keys = sorted(k for k in required if k not in export_paths)
    if missing_keys:
        raise SystemExit(f"Missing export_paths entries: {missing_keys}")
    missing = [k for k in sorted(required) if not export_paths[k].exists()]
    if missing:
        raise SystemExit(f"Missing expected export snapshot files: {missing}")

    # Pivot into (date, origin_key) -> value dicts for the selected metric_key variants.
    buckets: dict[tuple[str, str], dict[str, str]] = {}
    counts = {
        "input_rows_total": 0,
        "rows_emitted": 0,
        "rows_filtered_missing_core_fields": 0,
        "rows_filtered_out_of_registry": 0,
        "rows_filtered_out_of_scope": 0,
        "rows_filtered_outside_window": 0,
    }
    metric_rows_selected = {
        "l2_fees_eth": 0,
        "rent_paid_eth": 0,
        "profit_eth": 0,
        "txcount": 0,
    }

    def _upsert(metric_alias: str, row: dict[str, object]) -> None:
        origin_key = str(row.get("origin_key"))
        if origin_key not in origin_to_rollup:
            counts["rows_filtered_out_of_registry"] += 1
            return
        rollup_id = origin_to_rollup[origin_key]
        if rollup_id not in in_scope_rollups or origin_key not in in_scope_origins:
            counts["rows_filtered_out_of_scope"] += 1
            return
        d = _parse_date(str(row.get("date")), label="export.date")
        if d < start_date or d > end_date:
            counts["rows_filtered_outside_window"] += 1
            return
        if not registry[rollup_id].includes(d):
            counts["rows_filtered_outside_window"] += 1
            return

        key = (_format_date(d), rollup_id)
        b = buckets.get(key)
        if b is None:
            b = {
                "date_utc": _format_date(d),
                "rollup_id": rollup_id,
                "l2_fees_eth": "",
                "rent_paid_eth": "",
                "profit_eth": "",
                "txcount": "",
            }
            buckets[key] = b

        if metric_alias == "txcount":
            try:
                ival = int(_coerce_float(row.get("value"), label="txcount"))
            except ValueError as exc:
                raise SystemExit(f"Invalid txcount int: {row.get('value')!r}") from exc
            if ival < 0:
                raise SystemExit(f"Negative txcount not allowed: {ival}")
            b["txcount"] = str(ival)
            return

        fval = _coerce_float(row.get("value"), label=metric_alias)
        # Fees/rent are non-negative by definition; profit may be negative (rent > fees).
        if metric_alias in {"l2_fees_eth", "rent_paid_eth"} and fval < 0:
            raise SystemExit(f"Negative values not allowed: {metric_alias}={fval} ({key})")
        b[metric_alias] = format(fval, "f")

    # fees
    for row in _load_export_rows(export_paths["fees"]):
        counts["input_rows_total"] += 1
        if row.get("metric_key") != METRIC_KEY_MAP["l2_fees_eth"]:
            continue
        metric_rows_selected["l2_fees_eth"] += 1
        _upsert("l2_fees_eth", row)

    # rent_paid (vendor; secondary)
    for row in _load_export_rows(export_paths["rent_paid"]):
        counts["input_rows_total"] += 1
        if row.get("metric_key") != METRIC_KEY_MAP["rent_paid_eth_vendor"]:
            continue
        metric_rows_selected["rent_paid_eth"] += 1
        _upsert("rent_paid_eth", row)

    # profit
    for row in _load_export_rows(export_paths["profit"]):
        counts["input_rows_total"] += 1
        if row.get("metric_key") != METRIC_KEY_MAP["profit_eth"]:
            continue
        metric_rows_selected["profit_eth"] += 1
        _upsert("profit_eth", row)

    # txcount (single)
    for row in _load_export_rows(export_paths["txcount"]):
        counts["input_rows_total"] += 1
        if row.get("metric_key") != METRIC_KEY_MAP["txcount"]:
            continue
        metric_rows_selected["txcount"] += 1
        _upsert("txcount", row)

    missing_metric_keys = [metric for metric, hit_count in metric_rows_selected.items() if hit_count == 0]
    if missing_metric_keys:
        raise SystemExit(
            "Missing required growthepie metric rows in snapshot "
            f"(possible source instability / metric key drift): {missing_metric_keys}"
        )
    for metric, hit_count in metric_rows_selected.items():
        counts[f"metric_rows_selected_{metric}"] = hit_count

    rows_all = list(buckets.values())
    rows_all.sort(key=lambda r: (r["date_utc"], r["rollup_id"]))
    rows: list[dict[str, str]] = []
    for row in rows_all:
        if row["l2_fees_eth"] == "" or row["rent_paid_eth"] == "":
            counts["rows_filtered_missing_core_fields"] += 1
            continue
        rows.append(row)

    counts["rows_emitted"] = len(rows)
    return rows, counts


def _write_vendor_panel_csv(path: Path, rows: list[dict[str, str]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=list(PANEL_COLUMNS),
            lineterminator="\n",
        )
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in w.fieldnames})


def _write_sample_csv_append_only(path: Path, rows: list[dict[str, str]]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing sample: {path}")
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=list(PANEL_COLUMNS),
            lineterminator="\n",
        )
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in w.fieldnames})


def _filter_rows_for_sample(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    allowed = set(SAMPLE_ROLLUPS)
    for r in rows:
        rid = r.get("rollup_id", "")
        if rid not in allowed:
            continue
        d = _parse_date(r.get("date_utc", ""), label="date_utc")
        if d < SAMPLE_WINDOW_START or d > SAMPLE_WINDOW_END:
            continue
        out.append(r)
    out.sort(key=lambda r: (r["date_utc"], r["rollup_id"]))
    return out


def cmd_run(
    *,
    run_date: date | None,
    from_snapshot: Path | None,
    registry_path: Path,
    out_processed_csv: Path,
    start_date: date,
    end_date: date,
    write_sample: bool,
    sample_out: Path,
    write_raw_manifest: bool,
    write_processed_manifest: bool,
) -> int:
    root = _repo_root()
    schema_fields, schema_required_fields = _assert_panel_contract_v1(schema_path=PANEL_SCHEMA_PATH)

    if (run_date is None) == (from_snapshot is None):
        raise SystemExit("Provide exactly one of --run-date (fetch) or --from-snapshot (offline rebuild).")

    registry = load_registry(registry_path)
    snapshot_dir: Path
    as_of: date

    raw_written: list[Path] = []
    if run_date is not None:
        as_of = run_date
        snapshot_dir = root / "data" / "raw" / "growthepie" / run_date.isoformat()
        raw_written = _snapshot_growthepie(run_date=run_date, out_dir=snapshot_dir)
    else:
        assert from_snapshot is not None
        snapshot_dir = from_snapshot if from_snapshot.is_absolute() else (root / from_snapshot)
        if not snapshot_dir.exists():
            raise SystemExit(f"--from-snapshot not found: {snapshot_dir}")
        # Best-effort infer as_of from folder name.
        try:
            as_of = _parse_date(snapshot_dir.name, label="snapshot_dir")
        except SystemExit:
            as_of = date.today()

    export_paths = _resolve_export_paths(snapshot_dir)
    rows, counts = build_vendor_panel(registry=registry, export_paths=export_paths, start_date=start_date, end_date=end_date)
    _assert_panel_rows(rows=rows, schema_fields=schema_fields, schema_required_fields=schema_required_fields)
    _write_vendor_panel_csv(out_processed_csv, rows)

    sample_rows = _filter_rows_for_sample(rows)
    _assert_panel_rows(rows=sample_rows, schema_fields=schema_fields, schema_required_fields=schema_required_fields)
    if write_sample:
        _write_sample_csv_append_only(sample_out, sample_rows)

    raw_manifest_path: Path | None = None
    if write_raw_manifest and run_date is not None:
        raw_manifest_path = _write_raw_manifest(source="growthepie", snapshot_dir=snapshot_dir.relative_to(root), as_of=as_of)

    if write_processed_manifest:
        manifest_inputs: list[Path] = []
        if raw_manifest_path is not None and raw_manifest_path.exists():
            manifest_inputs.append(raw_manifest_path)
        manifest_inputs.append(registry_path)
        meta = {
            "source": "growthepie",
            "endpoints": {"master": MASTER_URL, "exports": EXPORT_ENDPOINTS},
            "metric_key_map": METRIC_KEY_MAP,
            "panel_schema_path": str(PANEL_SCHEMA_PATH.relative_to(root)),
            "panel_schema_fields": list(schema_fields),
            "panel_schema_required_fields": list(schema_required_fields),
            "date_range_utc": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "sample_window_utc": {"start": SAMPLE_WINDOW_START.isoformat(), "end": SAMPLE_WINDOW_END.isoformat()},
            "sample_rollups": list(SAMPLE_ROLLUPS),
            "counts": counts,
            "raw_written_files": [str(p.relative_to(root)) for p in raw_written] if raw_written else [],
            "sample_rows_emitted": len(sample_rows),
        }
        _write_processed_manifest(
            name="growthepie_vendor_daily_rollup_panel",
            as_of=as_of,
            inputs=[p.relative_to(root) if p.is_absolute() else p for p in manifest_inputs],
            outputs=[out_processed_csv.relative_to(root) if out_processed_csv.is_absolute() else out_processed_csv],
            meta=meta,
        )

    print(
        json.dumps(
            {
                "ok": True,
                "snapshot_dir": str(snapshot_dir),
                "out_processed_csv": str(out_processed_csv),
                "counts": counts,
                "sample": {"rows": len(sample_rows), "out": str(sample_out) if write_sample else None},
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="growthepie_fetch.py")
    p.add_argument("--discover", action="store_true", help="Print curlable discovery metadata and exit")
    p.add_argument("--run-date", default=None, help="UTC run date for snapshot folder naming (YYYY-MM-DD)")
    p.add_argument("--from-snapshot", default=None, help="Offline mode: path to an existing raw snapshot dir")
    p.add_argument("--registry", default="registry/rollup_registry_v1.csv")
    p.add_argument("--start-date", default="2022-01-01", help="Start date (UTC) for normalized panel (YYYY-MM-DD)")
    p.add_argument("--end-date", default=None, help="End date (UTC) for normalized panel (YYYY-MM-DD; default=run-date/today)")
    p.add_argument("--out-processed", default="data/processed/growthepie/vendor_daily_rollup_panel.csv")

    p.add_argument("--write-sample", action="store_true", help="Write the committed golden sample CSV (append-only; refuses overwrite)")
    p.add_argument("--sample-out", default="data/samples/growthepie/vendor_daily_rollup_panel_sample.csv")

    p.add_argument("--write-raw-manifest", action="store_true", help="Write data/raw_manifest/growthepie_<run-date>.json (requires --run-date)")
    p.add_argument("--write-processed-manifest", action="store_true", help="Write data/processed_manifest/growthepie_vendor_daily_rollup_panel_<as-of>.json")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.discover:
        return cmd_discover()

    run_date = _parse_date(args.run_date, label="run_date") if args.run_date else None
    from_snapshot = Path(args.from_snapshot) if args.from_snapshot else None
    registry_path = Path(args.registry)
    out_processed_csv = Path(args.out_processed)

    start_date = _parse_date(args.start_date, label="start_date")
    end_date = _parse_date(args.end_date, label="end_date") if args.end_date else (run_date or date.today())

    return cmd_run(
        run_date=run_date,
        from_snapshot=from_snapshot,
        registry_path=(registry_path if registry_path.is_absolute() else (REPO_ROOT / registry_path)),
        out_processed_csv=(out_processed_csv if out_processed_csv.is_absolute() else (REPO_ROOT / out_processed_csv)),
        start_date=start_date,
        end_date=end_date,
        write_sample=bool(args.write_sample),
        sample_out=(Path(args.sample_out) if Path(args.sample_out).is_absolute() else (REPO_ROOT / Path(args.sample_out))),
        write_raw_manifest=bool(args.write_raw_manifest),
        write_processed_manifest=bool(args.write_processed_manifest),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
