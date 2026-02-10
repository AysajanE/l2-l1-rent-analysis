from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.analysis.metrics_str import parse_optional_float  # noqa: E402
from src.etl.eip4844 import base_fee_per_blob_gas_wei_from_excess_blob_gas  # noqa: E402
from src.validation.reporting import ValidationFailure, exit_code_for, write_json, write_md  # noqa: E402


DENCUN_DATE_UTC = date(2024, 3, 13)
EPS = 1e-9
WEI_PER_ETH = Decimal("1000000000000000000")

DEFAULT_REGISTRY_CSV = REPO_ROOT / "registry" / "rollup_registry_v1.csv"
DEFAULT_OUT_JSON = REPO_ROOT / "reports" / "validation" / "universe_coverage.json"
DEFAULT_OUT_MD = REPO_ROOT / "reports" / "validation" / "universe_coverage.md"

SAMPLE_COSTS_CANDIDATES = [
    REPO_ROOT / "data" / "samples" / "l1" / "rollup_costs_daily_sample.csv",
    REPO_ROOT / "data" / "processed" / "onchain" / "rollup_costs_daily.parquet",
    REPO_ROOT / "data" / "processed" / "onchain" / "rollup_costs_daily.csv",
]
FULL_COSTS_CANDIDATES = [
    REPO_ROOT / "data" / "processed" / "onchain" / "rollup_costs_daily.parquet",
    REPO_ROOT / "data" / "processed" / "onchain" / "rollup_costs_daily.csv",
]

SAMPLE_DECOMP_CANDIDATES = [
    REPO_ROOT / "data" / "samples" / "l1" / "rollup_costs_decomposition_daily_sample.csv",
    REPO_ROOT / "data" / "samples" / "panels" / "daily_rollup_panel_v2_sample.csv",
    REPO_ROOT / "data" / "processed" / "onchain" / "rollup_costs_decomposition_daily.parquet",
    REPO_ROOT / "data" / "processed" / "onchain" / "rollup_costs_decomposition_daily.csv",
]
FULL_DECOMP_CANDIDATES = [
    REPO_ROOT / "data" / "processed" / "onchain" / "rollup_costs_decomposition_daily.parquet",
    REPO_ROOT / "data" / "processed" / "onchain" / "rollup_costs_decomposition_daily.csv",
]

SAMPLE_L1_CANDIDATES = [
    REPO_ROOT / "data" / "samples" / "panels" / "daily_rollup_panel_v2_sample.csv",
    REPO_ROOT / "data" / "samples" / "l1" / "l1_blocks_sample.csv",
    REPO_ROOT / "data" / "samples" / "blobscan" / "blobscan_daily_sample.csv",
    REPO_ROOT / "data" / "processed" / "l1" / "l1_blocks.parquet",
    REPO_ROOT / "data" / "processed" / "l1" / "l1_blocks.csv",
]
FULL_L1_CANDIDATES = [
    REPO_ROOT / "data" / "processed" / "l1" / "l1_blocks.parquet",
    REPO_ROOT / "data" / "processed" / "l1" / "l1_blocks.csv",
    REPO_ROOT / "data" / "processed" / "blobscan" / "blobscan_daily.parquet",
    REPO_ROOT / "data" / "processed" / "blobscan" / "blobscan_daily.csv",
]

SAMPLE_BLOBSCAN_CANDIDATES = [
    REPO_ROOT / "data" / "samples" / "blobscan" / "blobscan_daily_sample.csv",
    REPO_ROOT / "data" / "processed" / "blobscan" / "blobscan_daily.parquet",
    REPO_ROOT / "data" / "processed" / "blobscan" / "blobscan_daily.csv",
]
FULL_BLOBSCAN_CANDIDATES = [
    REPO_ROOT / "data" / "processed" / "blobscan" / "blobscan_daily.parquet",
    REPO_ROOT / "data" / "processed" / "blobscan" / "blobscan_daily.csv",
]


class InputSchemaError(ValueError):
    pass


@dataclass(frozen=True)
class RegistryRollup:
    rollup_id: str
    in_scope: bool
    status: str
    start_date_utc: date | None
    end_date_utc: date | None
    coverage_state: str
    address_count: int

    def active_in_range(self, *, start: date, end: date) -> bool:
        if not self.in_scope:
            return False
        if self.status == "deprecated":
            return False
        if self.status == "inactive" and self.end_date_utc is None:
            return False
        active_start = self.start_date_utc or date.min
        active_end = self.end_date_utc or date.max
        return active_start <= end and active_end >= start


def _rel(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except Exception:
        return str(path)


def _safe_float(value: float | None, *, ndigits: int = 12) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return round(value, ndigits)


def _parse_bool(value: Any, *, label: str) -> bool:
    s = str(value).strip().lower()
    if s in {"true", "1", "yes", "y"}:
        return True
    if s in {"false", "0", "no", "n"}:
        return False
    raise InputSchemaError(f"{label}: invalid boolean value {value!r}")


def _parse_optional_date(value: Any, *, label: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if s == "" or s.lower() in {"null", "none", "na", "nan"}:
        return None
    if "T" in s:
        s = s.split("T", 1)[0]
    try:
        return date.fromisoformat(s)
    except ValueError as exc:
        raise InputSchemaError(f"{label}: invalid date {value!r}") from exc


def _parse_required_date(value: Any, *, label: str) -> date:
    d = _parse_optional_date(value, label=label)
    if d is None:
        raise InputSchemaError(f"{label}: missing date")
    return d


def _parse_optional_int(value: Any, *, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise InputSchemaError(f"{label}: boolean is not a valid integer")
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not value.is_integer():
            raise InputSchemaError(f"{label}: non-integer float {value!r}")
        return int(value)
    s = str(value).strip()
    if s == "" or s.lower() in {"null", "none", "na", "nan"}:
        return None
    try:
        if "." in s:
            f = float(s)
            if not f.is_integer():
                raise InputSchemaError(f"{label}: non-integer numeric {value!r}")
            return int(f)
        return int(s)
    except ValueError as exc:
        raise InputSchemaError(f"{label}: invalid integer {value!r}") from exc


def _load_csv(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("missing_header")
        rows = [dict(r) for r in reader]
        return list(reader.fieldnames), rows


def _load_parquet(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        import pyarrow.parquet as pq  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency availability is environment-specific
        raise ValueError(f"pyarrow_unavailable: {exc}") from exc

    table = pq.read_table(path)
    rows = [dict(r) for r in table.to_pylist()]
    return list(table.schema.names), rows


def _load_table(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    if path.suffix.lower() != ".parquet":
        return _load_csv(path)

    errors: list[str] = []
    try:
        return _load_parquet(path)
    except Exception as exc:
        errors.append(f"parquet_read_failed: {exc}")
    try:
        return _load_csv(path)
    except Exception as exc:
        errors.append(f"csv_fallback_failed: {exc}")
    raise ValueError("; ".join(errors))


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for p in paths:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _candidate_paths(explicit_path: Path | None, defaults: list[Path]) -> list[Path]:
    candidates: list[Path] = []
    if explicit_path is not None:
        candidates.append(explicit_path)
    candidates.extend(defaults)
    return _dedupe_paths(candidates)


def _select_required_dataset(
    *,
    source: str,
    candidates: list[Path],
    parser: Callable[[Path, list[str], list[dict[str, Any]]], dict[str, Any]],
    failures: list[ValidationFailure],
    missing_inputs: list[str],
) -> tuple[Path | None, dict[str, Any] | None]:
    parse_errors: list[dict[str, str]] = []
    schema_errors: list[dict[str, str]] = []
    existing_any = False

    for path in candidates:
        if not path.exists():
            continue
        existing_any = True
        try:
            fieldnames, rows = _load_table(path)
        except Exception as exc:
            parse_errors.append({"path": _rel(path) or str(path), "error": str(exc)})
            continue
        try:
            parsed = parser(path, fieldnames, rows)
        except InputSchemaError as exc:
            schema_errors.append({"path": _rel(path) or str(path), "error": str(exc)})
            continue
        parsed["fieldnames"] = fieldnames
        parsed["rows"] = rows
        return path, parsed

    selected = candidates[0] if candidates else None
    selected_rel = _rel(selected) or source
    if selected_rel not in missing_inputs:
        missing_inputs.append(selected_rel)

    if not existing_any:
        failures.append(
            ValidationFailure(
                check="inputs",
                message="missing_input_file",
                details={"source": source, "candidates": [(_rel(p) or str(p)) for p in candidates]},
            )
        )
    elif parse_errors:
        failures.append(
            ValidationFailure(
                check="inputs",
                message="invalid_input_format",
                details={"source": source, "errors": parse_errors[:5]},
            )
        )
    elif schema_errors:
        failures.append(
            ValidationFailure(
                check="schema",
                message="input_schema_mismatch",
                details={"source": source, "errors": schema_errors[:5]},
            )
        )
    else:
        failures.append(ValidationFailure(check="inputs", message="unable_to_load_input", details={"source": source}))

    return None, None


def _select_optional_blobscan(
    *,
    candidates: list[Path],
    skip_path: Path | None,
) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    for path in candidates:
        if skip_path is not None and path.resolve() == skip_path.resolve():
            continue
        if not path.exists():
            continue
        try:
            fieldnames, rows = _load_table(path)
            parsed = _parse_blobscan(path, fieldnames, rows)
            parsed["fieldnames"] = fieldnames
            parsed["rows"] = rows
            return path, parsed, None
        except Exception as exc:
            return path, None, str(exc)
    return None, None, None


def _parse_registry(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    required = {"rollup_id", "in_scope", "batcher_addresses_json", "status", "start_date_utc", "end_date_utc"}
    missing_cols = sorted(c for c in required if c not in set(fieldnames))
    if missing_cols:
        raise InputSchemaError(f"{_rel(path)}: missing required columns {missing_cols}")

    rollups: list[RegistryRollup] = []
    state_counts: dict[str, int] = defaultdict(int)
    total_address_count = 0

    for i, row in enumerate(rows):
        row_ptr = f"{_rel(path)}:row:{i}"
        rollup_id = str(row.get("rollup_id", "")).strip()
        if rollup_id == "":
            raise InputSchemaError(f"{row_ptr}: missing rollup_id")

        in_scope = _parse_bool(row.get("in_scope"), label=f"{row_ptr}.in_scope")
        status = str(row.get("status", "")).strip().lower()
        if status == "":
            status = "active"
        start_date = _parse_optional_date(row.get("start_date_utc"), label=f"{row_ptr}.start_date_utc")
        end_date = _parse_optional_date(row.get("end_date_utc"), label=f"{row_ptr}.end_date_utc")
        if start_date is not None and end_date is not None and end_date < start_date:
            raise InputSchemaError(f"{row_ptr}: end_date_utc before start_date_utc")

        raw_json = row.get("batcher_addresses_json")
        coverage_state = "missing"
        address_count = 0
        if raw_json is not None and str(raw_json).strip() != "":
            try:
                parsed = json.loads(str(raw_json))
            except Exception as exc:
                raise InputSchemaError(f"{row_ptr}: invalid batcher_addresses_json ({exc})") from exc
            if not isinstance(parsed, dict):
                raise InputSchemaError(f"{row_ptr}: batcher_addresses_json must be an object")
            state_raw = parsed.get("state")
            coverage_state = str(state_raw).strip().lower() if state_raw is not None else "unknown"
            addresses = parsed.get("addresses", [])
            if not isinstance(addresses, list):
                raise InputSchemaError(f"{row_ptr}: batcher_addresses_json.addresses must be a list")
            address_count = len(addresses)

        rr = RegistryRollup(
            rollup_id=rollup_id,
            in_scope=in_scope,
            status=status,
            start_date_utc=start_date,
            end_date_utc=end_date,
            coverage_state=coverage_state,
            address_count=address_count,
        )
        rollups.append(rr)
        if in_scope:
            state_counts[coverage_state] += 1
            total_address_count += address_count

    in_scope_rollups = [r for r in rollups if r.in_scope]
    unknown_rollups = sorted([r.rollup_id for r in in_scope_rollups if r.coverage_state in {"unknown", "missing"}])
    partial_rollups = sorted([r.rollup_id for r in in_scope_rollups if r.coverage_state == "partial"])
    zero_addr_rollups = sorted([r.rollup_id for r in in_scope_rollups if r.address_count == 0])

    return {
        "path": _rel(path),
        "rollups": rollups,
        "in_scope_rollup_ids": {r.rollup_id for r in in_scope_rollups},
        "in_scope_rollup_count": len(in_scope_rollups),
        "state_counts": dict(sorted(state_counts.items())),
        "total_address_count": total_address_count,
        "rollups_with_unknown_state": unknown_rollups,
        "rollups_with_partial_state": partial_rollups,
        "rollups_with_zero_addresses": zero_addr_rollups,
    }


def _parse_costs(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    required = {"date_utc", "rollup_id", "rent_paid_eth"}
    missing_cols = sorted(c for c in required if c not in set(fieldnames))
    if missing_cols:
        raise InputSchemaError(f"{_rel(path)}: missing required columns {missing_cols}")

    dates: set[str] = set()
    rollups: set[str] = set()
    post_dencun_rows = 0

    for i, row in enumerate(rows):
        row_ptr = f"{_rel(path)}:row:{i}"
        d = _parse_required_date(row.get("date_utc"), label=f"{row_ptr}.date_utc")
        rollup_id = str(row.get("rollup_id", "")).strip()
        if rollup_id == "":
            raise InputSchemaError(f"{row_ptr}: missing rollup_id")
        try:
            rent_paid = parse_optional_float(row.get("rent_paid_eth"))
        except Exception as exc:
            raise InputSchemaError(f"{row_ptr}: invalid rent_paid_eth ({exc})") from exc
        if rent_paid is not None and rent_paid < 0:
            raise InputSchemaError(f"{row_ptr}: negative rent_paid_eth")

        dates.add(d.isoformat())
        rollups.add(rollup_id)
        if d >= DENCUN_DATE_UTC:
            post_dencun_rows += 1

    return {
        "path": _rel(path),
        "rows_total": len(rows),
        "unique_dates": len(dates),
        "unique_rollups": len(rollups),
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "post_dencun_rows": post_dencun_rows,
    }


def _parse_rollup_blob_usage(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, Any]],
    *,
    in_scope_rollups: set[str],
) -> dict[str, Any]:
    required = {"date_utc", "rollup_id", "rollup_blob_gas_used"}
    missing_cols = sorted(c for c in required if c not in set(fieldnames))
    if missing_cols:
        raise InputSchemaError(f"{_rel(path)}: missing required columns {missing_cols}")

    has_burn_column = "rent_blob_fee_burn_eth" in set(fieldnames)
    gas_by_date: dict[str, int] = defaultdict(int)
    burn_by_date: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    unknown_rollups: set[str] = set()
    rows_post_dencun = 0

    for i, row in enumerate(rows):
        row_ptr = f"{_rel(path)}:row:{i}"
        d = _parse_required_date(row.get("date_utc"), label=f"{row_ptr}.date_utc")
        if d < DENCUN_DATE_UTC:
            continue
        rows_post_dencun += 1

        rollup_id = str(row.get("rollup_id", "")).strip()
        if rollup_id == "":
            raise InputSchemaError(f"{row_ptr}: missing rollup_id")
        if rollup_id not in in_scope_rollups:
            unknown_rollups.add(rollup_id)
            continue

        gas = _parse_optional_int(row.get("rollup_blob_gas_used"), label=f"{row_ptr}.rollup_blob_gas_used")
        if gas is None:
            gas = 0
        if gas < 0:
            raise InputSchemaError(f"{row_ptr}: negative rollup_blob_gas_used")

        key = d.isoformat()
        gas_by_date[key] += int(gas)

        if has_burn_column:
            try:
                burn_eth = parse_optional_float(row.get("rent_blob_fee_burn_eth"))
            except Exception as exc:
                raise InputSchemaError(f"{row_ptr}: invalid rent_blob_fee_burn_eth ({exc})") from exc
            if burn_eth is not None:
                if burn_eth < 0:
                    raise InputSchemaError(f"{row_ptr}: negative rent_blob_fee_burn_eth")
                burn_by_date[key] += Decimal(str(burn_eth))

    return {
        "path": _rel(path),
        "rows_post_dencun": rows_post_dencun,
        "gas_by_date": dict(sorted(gas_by_date.items())),
        "burn_by_date": dict(sorted(burn_by_date.items())),
        "has_burn": has_burn_column and len(burn_by_date) > 0,
        "rollup_ids_not_in_registry": sorted(unknown_rollups),
    }


def _parse_l1_blob_baseline(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    field_set = set(fieldnames)
    if "date_utc" not in field_set:
        raise InputSchemaError(f"{_rel(path)}: missing required column date_utc")

    gas_col: str | None = None
    for c in ["l1_blob_gas_used", "blob_gas_used"]:
        if c in field_set:
            gas_col = c
            break
    if gas_col is None:
        raise InputSchemaError(f"{_rel(path)}: missing blob gas column (expected one of l1_blob_gas_used/blob_gas_used)")

    burn_direct_col = "l1_blob_fee_burn_eth" if "l1_blob_fee_burn_eth" in field_set else None
    base_fee_col: str | None = None
    for c in ["l1_blob_base_fee_wei", "base_fee_per_blob_gas_wei"]:
        if c in field_set:
            base_fee_col = c
            break
    has_excess_blob = "excess_blob_gas" in field_set

    panel_like = ("rollup_id" in field_set) and (gas_col == "l1_blob_gas_used")
    daily_panel_singletons: dict[str, tuple[int, Decimal | None]] = {}

    gas_by_date: dict[str, int] = defaultdict(int)
    burn_by_date: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    rows_post_dencun = 0
    burn_source_hits: set[str] = set()

    for i, row in enumerate(rows):
        row_ptr = f"{_rel(path)}:row:{i}"
        d = _parse_required_date(row.get("date_utc"), label=f"{row_ptr}.date_utc")
        if d < DENCUN_DATE_UTC:
            continue
        rows_post_dencun += 1

        gas = _parse_optional_int(row.get(gas_col), label=f"{row_ptr}.{gas_col}")
        if gas is None:
            continue
        if gas < 0:
            raise InputSchemaError(f"{row_ptr}: negative {gas_col}")

        burn_eth: Decimal | None = None
        if burn_direct_col is not None:
            try:
                burn_value = parse_optional_float(row.get(burn_direct_col))
            except Exception as exc:
                raise InputSchemaError(f"{row_ptr}: invalid {burn_direct_col} ({exc})") from exc
            if burn_value is not None:
                if burn_value < 0:
                    raise InputSchemaError(f"{row_ptr}: negative {burn_direct_col}")
                burn_eth = Decimal(str(burn_value))
                burn_source_hits.add(burn_direct_col)
        else:
            base_fee_wei: int | None = None
            if base_fee_col is not None:
                base_fee_wei = _parse_optional_int(row.get(base_fee_col), label=f"{row_ptr}.{base_fee_col}")
            if base_fee_wei is None and has_excess_blob:
                excess = _parse_optional_int(row.get("excess_blob_gas"), label=f"{row_ptr}.excess_blob_gas")
                if excess is not None:
                    if excess < 0:
                        raise InputSchemaError(f"{row_ptr}: negative excess_blob_gas")
                    base_fee_wei = base_fee_per_blob_gas_wei_from_excess_blob_gas(int(excess))
                    burn_source_hits.add("excess_blob_gas")
            elif base_fee_wei is not None:
                burn_source_hits.add(str(base_fee_col))

            if base_fee_wei is not None:
                if base_fee_wei < 0:
                    raise InputSchemaError(f"{row_ptr}: negative blob base fee")
                burn_eth = (Decimal(int(gas)) * Decimal(int(base_fee_wei))) / WEI_PER_ETH

        key = d.isoformat()
        if panel_like:
            prev = daily_panel_singletons.get(key)
            if prev is None:
                daily_panel_singletons[key] = (int(gas), burn_eth)
            else:
                prev_gas, prev_burn = prev
                if prev_gas != int(gas):
                    raise InputSchemaError(f"{row_ptr}: inconsistent {gas_col} across duplicate date rows ({key})")
                if prev_burn is not None and burn_eth is not None and abs(prev_burn - burn_eth) > Decimal("0.000000000001"):
                    raise InputSchemaError(f"{row_ptr}: inconsistent blob burn proxy across duplicate date rows ({key})")
                if prev_burn is None and burn_eth is not None:
                    daily_panel_singletons[key] = (prev_gas, burn_eth)
            continue

        gas_by_date[key] += int(gas)
        if burn_eth is not None:
            burn_by_date[key] += burn_eth

    if panel_like:
        for d, (gas, burn_eth) in sorted(daily_panel_singletons.items()):
            gas_by_date[d] = int(gas)
            if burn_eth is not None:
                burn_by_date[d] = burn_eth

    if burn_direct_col is not None:
        burn_source = burn_direct_col
    elif base_fee_col is not None:
        burn_source = f"{gas_col}*{base_fee_col}"
    elif has_excess_blob:
        burn_source = f"{gas_col}*base_fee_per_blob_gas_wei_from_excess_blob_gas(excess_blob_gas)"
    else:
        burn_source = None

    return {
        "path": _rel(path),
        "rows_post_dencun": rows_post_dencun,
        "gas_by_date": dict(sorted(gas_by_date.items())),
        "burn_by_date": dict(sorted(burn_by_date.items())),
        "burn_source": burn_source,
        "burn_source_hits": sorted(burn_source_hits),
        "panel_like": panel_like,
        "gas_column": gas_col,
    }


def _parse_blobscan(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    required = {"date_utc", "l1_blob_gas_used"}
    missing_cols = sorted(c for c in required if c not in set(fieldnames))
    if missing_cols:
        raise InputSchemaError(f"{_rel(path)}: missing required columns {missing_cols}")

    gas_by_date: dict[str, int] = defaultdict(int)
    for i, row in enumerate(rows):
        row_ptr = f"{_rel(path)}:row:{i}"
        d = _parse_required_date(row.get("date_utc"), label=f"{row_ptr}.date_utc")
        if d < DENCUN_DATE_UTC:
            continue
        gas = _parse_optional_int(row.get("l1_blob_gas_used"), label=f"{row_ptr}.l1_blob_gas_used")
        if gas is None:
            continue
        if gas < 0:
            raise InputSchemaError(f"{row_ptr}: negative l1_blob_gas_used")
        gas_by_date[d.isoformat()] += int(gas)

    return {"path": _rel(path), "gas_by_date": dict(sorted(gas_by_date.items()))}


def _build_md(report: dict[str, Any]) -> str:
    ok = bool(report.get("ok"))
    metrics = report.get("metrics", {})
    failures = report.get("failures") or []

    missing_inputs: list[str] = []
    if isinstance(metrics, dict):
        raw_missing = metrics.get("missing_inputs") or []
        if isinstance(raw_missing, list):
            missing_inputs = [str(x) for x in raw_missing]

    status = "PASS" if ok else ("MISSING INPUTS/SCHEMA" if missing_inputs else "FAIL")
    mode = metrics.get("mode", "unknown") if isinstance(metrics, dict) else "unknown"

    lines: list[str] = []
    lines.append("# Universe coverage report")
    lines.append("")
    lines.append(f"- Status: **{status}**")
    lines.append(f"- Mode: `{mode}`")
    lines.append(f"- Post-Dencun boundary: `{DENCUN_DATE_UTC.isoformat()}`")
    lines.append("")

    lines.append("## Inputs")
    for inp in report.get("inputs", []) or []:
        if not isinstance(inp, dict):
            continue
        lines.append(
            f"- `{inp.get('name')}`: `{inp.get('path')}` "
            f"(exists={inp.get('exists')}, required={inp.get('required')})"
        )
    lines.append("")

    if isinstance(metrics, dict):
        registry = metrics.get("registry", {})
        if isinstance(registry, dict):
            lines.append("## Registry readiness")
            for k in [
                "in_scope_rollup_count",
                "active_in_scope_rollup_count_in_observed_post_dencun_window",
                "total_address_count",
            ]:
                if k in registry:
                    lines.append(f"- {k}: {registry.get(k)}")
            state_counts = registry.get("address_coverage_state_counts")
            if isinstance(state_counts, dict):
                lines.append(f"- address_coverage_state_counts: {state_counts}")
            lines.append("")

        attribution = metrics.get("attribution", {})
        if isinstance(attribution, dict):
            agg = attribution.get("aggregate", {})
            lines.append("## Attribution coverage (post-Dencun)")
            if isinstance(agg, dict):
                for k in [
                    "dates_with_l1_blob_baseline",
                    "dates_with_rollup_blob_usage",
                    "dates_missing_rollup_blob_usage",
                    "sum_rollup_blob_gas_used",
                    "sum_l1_blob_gas_used",
                    "rollup_to_l1_blob_gas_ratio",
                ]:
                    if k in agg:
                        lines.append(f"- {k}: {agg.get(k)}")
                if "sum_rollup_blob_fee_burn_eth" in agg:
                    lines.append(f"- sum_rollup_blob_fee_burn_eth: {agg.get('sum_rollup_blob_fee_burn_eth')}")
                if "sum_l1_blob_fee_burn_proxy_eth" in agg:
                    lines.append(f"- sum_l1_blob_fee_burn_proxy_eth: {agg.get('sum_l1_blob_fee_burn_proxy_eth')}")
                if "rollup_to_l1_blob_fee_burn_ratio" in agg:
                    lines.append(f"- rollup_to_l1_blob_fee_burn_ratio: {agg.get('rollup_to_l1_blob_fee_burn_ratio')}")
            lines.append("")

            gaps = attribution.get("gaps", {})
            if isinstance(gaps, dict):
                lines.append("## Gaps")
                for k in [
                    "rollups_with_unknown_state",
                    "rollups_with_partial_state",
                    "rollup_ids_not_in_registry",
                ]:
                    if k in gaps:
                        lines.append(f"- {k}: {gaps.get(k)}")
                coverage_drop_dates = gaps.get("coverage_drop_dates") or []
                if isinstance(coverage_drop_dates, list):
                    if coverage_drop_dates:
                        lines.append("- coverage_drop_dates (first 20):")
                        for item in coverage_drop_dates[:20]:
                            if isinstance(item, dict):
                                lines.append(f"  - {item.get('date_utc')}: ratio={item.get('coverage_ratio')}")
                    else:
                        lines.append("- coverage_drop_dates: []")
                lines.append("")

    if failures:
        lines.append("## Failures")
        for f in failures[:50]:
            if not isinstance(f, dict):
                continue
            details = f.get("details")
            if isinstance(details, dict):
                lines.append(f"- [{f.get('check')}] {f.get('message')} :: {details}")
            else:
                lines.append(f"- [{f.get('check')}] {f.get('message')}")
        if len(failures) > 50:
            lines.append(f"- (truncated; total failures={len(failures)})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run_report(
    *,
    mode: str,
    registry_csv: Path,
    costs_candidates: list[Path],
    decomp_candidates: list[Path],
    l1_candidates: list[Path],
    blobscan_candidates: list[Path],
    out_json: Path,
    out_md: Path,
) -> int:
    failures: list[ValidationFailure] = []
    missing_inputs: list[str] = []

    registry_path, registry = _select_required_dataset(
        source="registry",
        candidates=_candidate_paths(registry_csv, []),
        parser=_parse_registry,
        failures=failures,
        missing_inputs=missing_inputs,
    )
    in_scope_rollups: set[str] = set()
    if registry is not None:
        in_scope_rollups = set(registry.get("in_scope_rollup_ids", set()))

    def _parse_rollup_with_registry(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
        return _parse_rollup_blob_usage(path, fieldnames, rows, in_scope_rollups=in_scope_rollups)

    costs_path, costs = _select_required_dataset(
        source="rollup_costs_daily",
        candidates=costs_candidates,
        parser=_parse_costs,
        failures=failures,
        missing_inputs=missing_inputs,
    )
    decomp_path, decomp = _select_required_dataset(
        source="rollup_blob_usage",
        candidates=decomp_candidates,
        parser=_parse_rollup_with_registry,
        failures=failures,
        missing_inputs=missing_inputs,
    )
    l1_path, l1 = _select_required_dataset(
        source="l1_blob_baseline",
        candidates=l1_candidates,
        parser=_parse_l1_blob_baseline,
        failures=failures,
        missing_inputs=missing_inputs,
    )

    blobscan_path, blobscan, blobscan_warning = _select_optional_blobscan(candidates=blobscan_candidates, skip_path=l1_path)

    inputs = [
        {
            "name": "registry",
            "path": _rel(registry_path or registry_csv),
            "exists": bool((registry_path or registry_csv).exists()),
            "required": True,
        },
        {
            "name": "rollup_costs_daily",
            "path": _rel(costs_path or costs_candidates[0]) if costs_candidates else None,
            "exists": bool((costs_path or (costs_candidates[0] if costs_candidates else None)) and (costs_path or costs_candidates[0]).exists()),
            "required": True,
        },
        {
            "name": "rollup_blob_usage",
            "path": _rel(decomp_path or decomp_candidates[0]) if decomp_candidates else None,
            "exists": bool((decomp_path or (decomp_candidates[0] if decomp_candidates else None)) and (decomp_path or decomp_candidates[0]).exists()),
            "required": True,
        },
        {
            "name": "l1_blob_baseline",
            "path": _rel(l1_path or l1_candidates[0]) if l1_candidates else None,
            "exists": bool((l1_path or (l1_candidates[0] if l1_candidates else None)) and (l1_path or l1_candidates[0]).exists()),
            "required": True,
        },
    ]
    if blobscan_path is not None:
        inputs.append({"name": "blobscan_optional", "path": _rel(blobscan_path), "exists": True, "required": False})

    metrics: dict[str, Any] = {
        "mode": mode,
        "post_dencun_start_utc": DENCUN_DATE_UTC.isoformat(),
        "missing_inputs": sorted(missing_inputs),
    }

    if registry is not None:
        observed_start: date | None = None
        observed_end: date | None = None
        if l1 is not None:
            l1_dates = sorted((l1.get("gas_by_date") or {}).keys())
            if l1_dates:
                observed_start = date.fromisoformat(l1_dates[0])
                observed_end = date.fromisoformat(l1_dates[-1])

        active_rollups = []
        if observed_start is not None and observed_end is not None:
            for r in registry.get("rollups", []):
                if isinstance(r, RegistryRollup) and r.active_in_range(start=observed_start, end=observed_end):
                    active_rollups.append(r.rollup_id)

        metrics["registry"] = {
            "in_scope_rollup_count": registry.get("in_scope_rollup_count"),
            "active_in_scope_rollup_count_in_observed_post_dencun_window": len(active_rollups),
            "address_coverage_state_counts": registry.get("state_counts", {}),
            "total_address_count": registry.get("total_address_count"),
            "rollups_with_unknown_state": registry.get("rollups_with_unknown_state", []),
            "rollups_with_partial_state": registry.get("rollups_with_partial_state", []),
            "rollups_with_zero_addresses": registry.get("rollups_with_zero_addresses", []),
        }

    if costs is not None:
        metrics["rollup_costs_daily"] = {
            "rows_total": costs.get("rows_total"),
            "unique_dates": costs.get("unique_dates"),
            "unique_rollups": costs.get("unique_rollups"),
            "date_min": costs.get("date_min"),
            "date_max": costs.get("date_max"),
            "post_dencun_rows": costs.get("post_dencun_rows"),
        }

    if not missing_inputs and decomp is not None and l1 is not None:
        rollup_gas_by_date: dict[str, int] = dict(decomp.get("gas_by_date") or {})
        l1_gas_by_date: dict[str, int] = dict(l1.get("gas_by_date") or {})
        rollup_burn_by_date: dict[str, Decimal] = dict(decomp.get("burn_by_date") or {})
        l1_burn_by_date: dict[str, Decimal] = dict(l1.get("burn_by_date") or {})

        l1_dates = sorted([d for d in l1_gas_by_date.keys() if date.fromisoformat(d) >= DENCUN_DATE_UTC])
        rollup_dates = sorted([d for d in rollup_gas_by_date.keys() if date.fromisoformat(d) >= DENCUN_DATE_UTC])

        daily_blob_gas_coverage: list[dict[str, Any]] = []
        coverage_drop_dates: list[dict[str, Any]] = []
        coverage_overshoot_dates: list[dict[str, Any]] = []
        sum_rollup_blob_gas_used = 0
        sum_l1_blob_gas_used = 0

        for d in l1_dates:
            l1_gas = int(l1_gas_by_date.get(d, 0))
            rollup_gas = int(rollup_gas_by_date.get(d, 0))
            if l1_gas <= 0:
                ratio = None
            else:
                ratio = float(rollup_gas / l1_gas)
                sum_rollup_blob_gas_used += rollup_gas
                sum_l1_blob_gas_used += l1_gas
                if ratio < (1.0 - EPS):
                    coverage_drop_dates.append({"date_utc": d, "coverage_ratio": _safe_float(ratio)})
                elif ratio > (1.0 + EPS):
                    coverage_overshoot_dates.append({"date_utc": d, "coverage_ratio": _safe_float(ratio)})

            daily_blob_gas_coverage.append(
                {
                    "date_utc": d,
                    "sum_rollup_blob_gas_used": rollup_gas,
                    "l1_blob_gas_used": l1_gas,
                    "coverage_ratio": _safe_float(ratio),
                }
            )

        agg_ratio = None
        if sum_l1_blob_gas_used > 0:
            agg_ratio = float(sum_rollup_blob_gas_used / sum_l1_blob_gas_used)

        sum_rollup_blob_fee_burn_eth: float | None = None
        sum_l1_blob_fee_burn_proxy_eth: float | None = None
        burn_ratio: float | None = None
        daily_blob_burn_coverage: list[dict[str, Any]] = []
        burn_overshoot_dates: list[dict[str, Any]] = []

        burn_days = sorted([d for d in l1_dates if d in l1_burn_by_date])
        if burn_days and len(rollup_burn_by_date) > 0:
            total_rollup_burn = Decimal("0")
            total_l1_burn = Decimal("0")
            for d in burn_days:
                l1_burn = l1_burn_by_date.get(d, Decimal("0"))
                rollup_burn = rollup_burn_by_date.get(d, Decimal("0"))
                ratio = None
                if l1_burn > 0:
                    ratio = float(rollup_burn / l1_burn)
                    if ratio > (1.0 + EPS):
                        burn_overshoot_dates.append({"date_utc": d, "coverage_ratio": _safe_float(ratio)})
                    total_rollup_burn += rollup_burn
                    total_l1_burn += l1_burn
                daily_blob_burn_coverage.append(
                    {
                        "date_utc": d,
                        "sum_rollup_blob_fee_burn_eth": _safe_float(float(rollup_burn)),
                        "l1_blob_fee_burn_proxy_eth": _safe_float(float(l1_burn)),
                        "coverage_ratio": _safe_float(ratio),
                    }
                )

            if total_l1_burn > 0:
                sum_rollup_blob_fee_burn_eth = float(total_rollup_burn)
                sum_l1_blob_fee_burn_proxy_eth = float(total_l1_burn)
                burn_ratio = float(total_rollup_burn / total_l1_burn)

        if coverage_overshoot_dates:
            failures.append(
                ValidationFailure(
                    check="attribution_consistency",
                    message="rollup_blob_gas_exceeds_l1_blob_gas",
                    details={"dates": coverage_overshoot_dates[:20], "count": len(coverage_overshoot_dates)},
                )
            )
        if burn_overshoot_dates:
            failures.append(
                ValidationFailure(
                    check="attribution_consistency",
                    message="rollup_blob_burn_exceeds_l1_blob_burn_proxy",
                    details={"dates": burn_overshoot_dates[:20], "count": len(burn_overshoot_dates)},
                )
            )

        gap_rollups_unknown = []
        gap_rollups_partial = []
        if isinstance(metrics.get("registry"), dict):
            gap_rollups_unknown = list(metrics["registry"].get("rollups_with_unknown_state") or [])
            gap_rollups_partial = list(metrics["registry"].get("rollups_with_partial_state") or [])

        gaps = {
            "rollups_with_unknown_state": gap_rollups_unknown,
            "rollups_with_partial_state": gap_rollups_partial,
            "rollup_ids_not_in_registry": decomp.get("rollup_ids_not_in_registry", []),
            "coverage_drop_dates": coverage_drop_dates,
            "coverage_overshoot_dates": coverage_overshoot_dates,
            "dates_missing_rollup_blob_usage": sorted([d for d in l1_dates if d not in rollup_gas_by_date]),
            "dates_missing_l1_blob_baseline": sorted([d for d in rollup_dates if d not in l1_gas_by_date]),
        }

        metrics["attribution"] = {
            "rollup_blob_usage_source": decomp.get("path"),
            "l1_blob_baseline_source": l1.get("path"),
            "l1_blob_burn_proxy_source": l1.get("burn_source"),
            "aggregate": {
                "dates_with_l1_blob_baseline": len(l1_dates),
                "dates_with_rollup_blob_usage": len(rollup_dates),
                "dates_missing_rollup_blob_usage": len(gaps["dates_missing_rollup_blob_usage"]),
                "sum_rollup_blob_gas_used": sum_rollup_blob_gas_used,
                "sum_l1_blob_gas_used": sum_l1_blob_gas_used,
                "rollup_to_l1_blob_gas_ratio": _safe_float(agg_ratio),
                "sum_rollup_blob_fee_burn_eth": _safe_float(sum_rollup_blob_fee_burn_eth),
                "sum_l1_blob_fee_burn_proxy_eth": _safe_float(sum_l1_blob_fee_burn_proxy_eth),
                "rollup_to_l1_blob_fee_burn_ratio": _safe_float(burn_ratio),
            },
            "daily_blob_gas_coverage": daily_blob_gas_coverage,
            "daily_blob_fee_burn_coverage": daily_blob_burn_coverage,
            "gaps": gaps,
        }

        if blobscan is not None:
            blobscan_gas = blobscan.get("gas_by_date") or {}
            overlap_dates = sorted(set(blobscan_gas.keys()) & set(l1_gas_by_date.keys()))
            blobscan_sum = sum(int(blobscan_gas[d]) for d in overlap_dates)
            l1_sum = sum(int(l1_gas_by_date[d]) for d in overlap_dates)
            triangulation_ratio = float(blobscan_sum / l1_sum) if l1_sum > 0 else None
            metrics["attribution"]["blobscan_triangulation"] = {
                "source": blobscan.get("path"),
                "days_overlap": len(overlap_dates),
                "sum_blobscan_l1_blob_gas_used": blobscan_sum,
                "sum_l1_baseline_blob_gas_used": l1_sum,
                "blobscan_to_l1_baseline_ratio": _safe_float(triangulation_ratio),
            }
        elif blobscan_warning is not None:
            metrics["attribution"]["blobscan_triangulation"] = {"status": "invalid_or_unreadable", "error": blobscan_warning}
        else:
            metrics["attribution"]["blobscan_triangulation"] = {"status": "not_available"}

    report = {
        "ok": (len(failures) == 0 and len(missing_inputs) == 0),
        "inputs": inputs,
        "metrics": metrics,
        "failures": [f.as_dict() for f in failures],
    }
    write_json(out_json, report)
    write_md(out_md, _build_md(report))
    return exit_code_for(ok=bool(report["ok"]), missing_inputs=missing_inputs)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="report_universe_coverage.py")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--sample", action="store_true", help="Run deterministic sample mode (default).")
    mode.add_argument("--full", action="store_true", help="Prefer data/processed inputs.")
    p.add_argument("--registry-csv", default=str(DEFAULT_REGISTRY_CSV), help="Rollup registry CSV path.")
    p.add_argument("--costs", default=None, help="Optional override for rollup_costs_daily table.")
    p.add_argument("--decomp", default=None, help="Optional override for rollup decomposition/source with blob usage.")
    p.add_argument("--l1-blocks", default=None, help="Optional override for L1 blob baseline table.")
    p.add_argument("--blobscan", default=None, help="Optional blobscan path for triangulation.")
    p.add_argument("--panel-v2", default=None, help="Optional panel v2 path used as fallback source in sample/full mode.")
    p.add_argument("--out-json", default=str(DEFAULT_OUT_JSON), help="Output JSON path.")
    p.add_argument("--out-md", default=str(DEFAULT_OUT_MD), help="Output Markdown path.")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    mode = "full" if bool(args.full) else "sample"

    registry_csv = Path(args.registry_csv)
    panel_v2_path = Path(args.panel_v2) if args.panel_v2 else None

    costs_defaults = FULL_COSTS_CANDIDATES if mode == "full" else SAMPLE_COSTS_CANDIDATES
    decomp_defaults = FULL_DECOMP_CANDIDATES if mode == "full" else SAMPLE_DECOMP_CANDIDATES
    l1_defaults = FULL_L1_CANDIDATES if mode == "full" else SAMPLE_L1_CANDIDATES
    blobscan_defaults = FULL_BLOBSCAN_CANDIDATES if mode == "full" else SAMPLE_BLOBSCAN_CANDIDATES

    if panel_v2_path is not None:
        decomp_defaults = [panel_v2_path] + decomp_defaults
        l1_defaults = [panel_v2_path] + l1_defaults

    costs_candidates = _candidate_paths(Path(args.costs) if args.costs else None, costs_defaults)
    decomp_candidates = _candidate_paths(Path(args.decomp) if args.decomp else None, decomp_defaults)

    l1_override = Path(args.l1_blocks) if args.l1_blocks else None
    l1_defaults_with_blobscan = list(l1_defaults)
    if args.blobscan and l1_override is None:
        l1_defaults_with_blobscan = [Path(args.blobscan)] + l1_defaults_with_blobscan
    l1_candidates = _candidate_paths(l1_override, l1_defaults_with_blobscan)

    blobscan_candidates = _candidate_paths(Path(args.blobscan) if args.blobscan else None, blobscan_defaults)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)

    try:
        return run_report(
            mode=mode,
            registry_csv=registry_csv,
            costs_candidates=costs_candidates,
            decomp_candidates=decomp_candidates,
            l1_candidates=l1_candidates,
            blobscan_candidates=blobscan_candidates,
            out_json=out_json,
            out_md=out_md,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback for CLI contract compliance
        fallback = {
            "ok": False,
            "inputs": [],
            "metrics": {
                "mode": mode,
                "post_dencun_start_utc": DENCUN_DATE_UTC.isoformat(),
                "missing_inputs": [],
            },
            "failures": [ValidationFailure(check="internal", message="unexpected_exception", details={"error": str(exc)}).as_dict()],
        }
        write_json(out_json, fallback)
        write_md(out_md, _build_md(fallback))
        return exit_code_for(ok=False, missing_inputs=[])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
