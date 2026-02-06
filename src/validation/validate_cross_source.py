from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.analysis.metrics_str import parse_optional_float  # noqa: E402
from src.validation.reporting import ValidationFailure, exit_code_for, write_json, write_md  # noqa: E402


MONTHLY_TOLERANCE_TARGET_LOW = 0.05
MONTHLY_TOLERANCE_TARGET_HIGH = 0.10
BLOB_GAS_TOLERANCE = 0.01

DEFAULT_TOP_K = 10

SAMPLE_GROWTHEPIE_CSV = REPO_ROOT / "data" / "samples" / "growthepie" / "vendor_daily_rollup_panel_sample.csv"
SAMPLE_ONCHAIN_CANDIDATES = [
    REPO_ROOT / "data" / "samples" / "onchain" / "rollup_costs_daily_sample.csv",
    REPO_ROOT / "data" / "samples" / "panels" / "daily_rollup_panel_v1_sample.csv",
    REPO_ROOT / "data" / "processed" / "onchain" / "rollup_costs_daily.csv",
]
SAMPLE_L2BEAT_CANDIDATES = [
    REPO_ROOT / "data" / "samples" / "l2beat" / "l2beat_costs_daily_sample.csv",
    REPO_ROOT / "data" / "processed" / "l2beat" / "l2beat_costs_daily.csv",
]

DEFAULT_OUT_JSON = REPO_ROOT / "reports" / "validation" / "cross_source_validation.json"
DEFAULT_OUT_MD = REPO_ROOT / "reports" / "validation" / "cross_source_validation.md"


def _rel(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except Exception:
        return str(path)


def _first_existing(candidates: list[Path]) -> Path:
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _add_missing_input(missing_inputs: list[str], item: str) -> None:
    if item not in missing_inputs:
        missing_inputs.append(item)


def _load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("missing_header")
        rows = [dict(r) for r in reader]
        return list(reader.fieldnames), rows


def _parse_month(date_utc: str) -> str | None:
    raw = date_utc.strip()
    if raw == "":
        return None
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        return None
    return f"{d.year:04d}-{d.month:02d}"


def _is_unknown_bucket(rollup_id: str) -> bool:
    s = rollup_id.strip().lower()
    return s in {"other", "unknown"} or ("unknown" in s) or ("unattributed" in s)


def _safe_pct_delta(*, lhs: float, rhs: float, denom_ref: float) -> float:
    if lhs == rhs == 0.0:
        return 0.0
    denom = max(abs(denom_ref), 1e-9)
    return abs(lhs - rhs) / denom


def _max_ref_pct_delta(*, lhs: float, rhs: float) -> float:
    if lhs == rhs == 0.0:
        return 0.0
    denom = max(abs(lhs), abs(rhs), 1e-9)
    return abs(lhs - rhs) / denom


def _build_md(report: dict[str, Any]) -> str:
    ok = bool(report.get("ok"))
    metrics = report.get("metrics", {})
    failures = report.get("failures") or []
    missing_inputs = []
    if isinstance(metrics, dict):
        raw_missing = metrics.get("missing_inputs") or []
        if isinstance(raw_missing, list):
            missing_inputs = [str(x) for x in raw_missing]

    status = "PASS" if ok else ("MISSING INPUTS/SCHEMA" if missing_inputs else "FAIL")
    mode = metrics.get("mode", "unknown") if isinstance(metrics, dict) else "unknown"

    lines: list[str] = []
    lines.append("# Cross-source validation")
    lines.append("")
    lines.append(f"- Status: **{status}**")
    lines.append(f"- Mode: `{mode}`")
    lines.append("")

    lines.append("## Inputs")
    for inp in report.get("inputs", []) or []:
        if not isinstance(inp, dict):
            continue
        label = inp.get("name")
        path = inp.get("path")
        exists = inp.get("exists")
        required = inp.get("required")
        lines.append(f"- `{label}`: `{path}` (exists={exists}, required={required})")
    lines.append("")

    if isinstance(metrics, dict):
        lines.append("## Metrics")
        monthly_summary = metrics.get("monthly_reconciliation_summary", {})
        if isinstance(monthly_summary, dict):
            for key in [
                "records_total",
                "records_le_5pct",
                "records_between_5pct_10pct",
                "records_gt_10pct",
                "top_rollup_count",
            ]:
                if key in monthly_summary:
                    lines.append(f"- {key}: {monthly_summary[key]}")
        blob = metrics.get("blob_gas_used_check", {})
        if isinstance(blob, dict):
            lines.append(f"- blob_gas_used_check_status: {blob.get('status')}")
            for key in ["selected_month_utc", "days_compared", "days_gt_1pct"]:
                if key in blob:
                    lines.append(f"- blob_{key}: {blob[key]}")
        unknowns = metrics.get("unknown_unattributed_rollups", {})
        if isinstance(unknowns, dict):
            lines.append(f"- unknown_unattributed_rollups: {unknowns}")
        lines.append("")

    if failures:
        lines.append("## Failures")
        for f in failures[:50]:
            if not isinstance(f, dict):
                continue
            details = f.get("details")
            if isinstance(details, dict) and "rollup_id" in details and "month_utc" in details:
                ptr = f" ({details.get('rollup_id')} @ {details.get('month_utc')})"
            elif isinstance(details, dict) and "date_utc" in details:
                ptr = f" ({details.get('date_utc')})"
            else:
                ptr = ""
            lines.append(f"- [{f.get('check')}] {f.get('message')}{ptr}")
        if len(failures) > 50:
            lines.append(f"- (truncated; total failures={len(failures)})")
        lines.append("")

    if not ok:
        lines.append("## Plausible causes")
        lines.append("- Source-window mismatch or stale snapshots (different extraction dates/ranges).")
        lines.append("- Rollup identifier mapping drift between vendor/on-chain/L2BEAT joins.")
        lines.append("- Attribution coverage differences (especially blob-heavy days).")
        lines.append("")
        lines.append("## Minimal next experiment")
        lines.append(
            "- Pick one failing rollup-month and compare daily values side-by-side from all sources, then verify ID mapping and source run dates."
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _validate_required_columns(
    *,
    source: str,
    fieldnames: list[str],
    required: set[str],
    failures: list[ValidationFailure],
    missing_inputs: list[str],
    input_path: Path | None,
) -> bool:
    missing_cols = sorted(c for c in required if c not in set(fieldnames))
    if not missing_cols:
        return True
    rel = _rel(input_path) or source
    _add_missing_input(missing_inputs, rel)
    failures.append(
        ValidationFailure(
            check="schema",
            message="missing_required_columns",
            details={"source": source, "path": rel, "missing_columns": missing_cols},
        )
    )
    return False


def _aggregate_monthly_rollup_metric(
    *,
    source: str,
    rows: list[dict[str, str]],
    value_col: str,
    failures: list[ValidationFailure],
    missing_inputs: list[str],
    input_path: Path | None,
) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = defaultdict(float)
    rel = _rel(input_path) or source
    for i, row in enumerate(rows):
        month = _parse_month(str(row.get("date_utc", "")))
        if month is None:
            _add_missing_input(missing_inputs, rel)
            if len(failures) < 200:
                failures.append(
                    ValidationFailure(
                        check="schema",
                        message="invalid_date_utc",
                        details={"source": source, "path": rel, "row": i, "value": row.get("date_utc")},
                    )
                )
            continue
        rollup_id = str(row.get("rollup_id", "")).strip()
        if rollup_id == "":
            _add_missing_input(missing_inputs, rel)
            if len(failures) < 200:
                failures.append(
                    ValidationFailure(
                        check="schema",
                        message="missing_rollup_id",
                        details={"source": source, "path": rel, "row": i},
                    )
                )
            continue
        raw_value = row.get(value_col)
        try:
            value = parse_optional_float(raw_value)
        except Exception:
            value = None
            _add_missing_input(missing_inputs, rel)
            if len(failures) < 200:
                failures.append(
                    ValidationFailure(
                        check="schema",
                        message="invalid_numeric",
                        details={
                            "source": source,
                            "path": rel,
                            "row": i,
                            "column": value_col,
                            "value": raw_value,
                        },
                    )
                )
        if value is None:
            continue
        if value < 0:
            if len(failures) < 200:
                failures.append(
                    ValidationFailure(
                        check="non_negativity",
                        message="negative_value",
                        details={
                            "source": source,
                            "path": rel,
                            "row": i,
                            "month_utc": month,
                            "rollup_id": rollup_id,
                            "column": value_col,
                            "value": value,
                        },
                    )
                )
            continue
        out[(month, rollup_id)] += float(value)
    return dict(out)


def _aggregate_rollup_fees_for_ranking(
    *,
    rows: list[dict[str, str]],
    failures: list[ValidationFailure],
    missing_inputs: list[str],
    input_path: Path | None,
) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    rel = _rel(input_path) or "growthepie"
    for i, row in enumerate(rows):
        rollup_id = str(row.get("rollup_id", "")).strip()
        if rollup_id == "":
            _add_missing_input(missing_inputs, rel)
            if len(failures) < 200:
                failures.append(
                    ValidationFailure(
                        check="schema",
                        message="missing_rollup_id",
                        details={"source": "growthepie", "path": rel, "row": i},
                    )
                )
            continue
        raw_value = row.get("l2_fees_eth")
        try:
            value = parse_optional_float(raw_value)
        except Exception:
            value = None
            _add_missing_input(missing_inputs, rel)
            if len(failures) < 200:
                failures.append(
                    ValidationFailure(
                        check="schema",
                        message="invalid_numeric",
                        details={
                            "source": "growthepie",
                            "path": rel,
                            "row": i,
                            "column": "l2_fees_eth",
                            "value": raw_value,
                        },
                    )
                )
        if value is None:
            continue
        if value < 0:
            if len(failures) < 200:
                failures.append(
                    ValidationFailure(
                        check="non_negativity",
                        message="negative_value",
                        details={
                            "source": "growthepie",
                            "path": rel,
                            "row": i,
                            "column": "l2_fees_eth",
                            "value": value,
                        },
                    )
                )
            continue
        out[rollup_id] += float(value)
    return dict(out)


def _select_top_rollups(fees_by_rollup: dict[str, float], top_k: int) -> list[str]:
    ranked = sorted(fees_by_rollup.items(), key=lambda kv: (-kv[1], kv[0]))
    return [rollup for rollup, _ in ranked[:top_k]]


def _detect_blob_column(fieldnames: list[str], *, source: str) -> str | None:
    cols = set(fieldnames)
    if source == "blobscan":
        for c in ["l1_blob_gas_used", "blob_gas_used"]:
            if c in cols:
                return c
        return None
    if source == "onchain_blob":
        for c in ["l1_blob_gas_used", "blob_gas_used", "rollup_blob_gas_used"]:
            if c in cols:
                return c
        return None
    return None


def _aggregate_daily_metric(
    *,
    source: str,
    rows: list[dict[str, str]],
    value_col: str,
    failures: list[ValidationFailure],
    missing_inputs: list[str],
    input_path: Path | None,
) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    rel = _rel(input_path) or source
    for i, row in enumerate(rows):
        d = str(row.get("date_utc", "")).strip()
        month = _parse_month(d)
        if month is None:
            _add_missing_input(missing_inputs, rel)
            if len(failures) < 200:
                failures.append(
                    ValidationFailure(
                        check="schema",
                        message="invalid_date_utc",
                        details={"source": source, "path": rel, "row": i, "value": row.get("date_utc")},
                    )
                )
            continue
        raw_value = row.get(value_col)
        try:
            value = parse_optional_float(raw_value)
        except Exception:
            value = None
            _add_missing_input(missing_inputs, rel)
            if len(failures) < 200:
                failures.append(
                    ValidationFailure(
                        check="schema",
                        message="invalid_numeric",
                        details={
                            "source": source,
                            "path": rel,
                            "row": i,
                            "column": value_col,
                            "value": raw_value,
                        },
                    )
                )
        if value is None:
            continue
        if value < 0:
            if len(failures) < 200:
                failures.append(
                    ValidationFailure(
                        check="non_negativity",
                        message="negative_value",
                        details={
                            "source": source,
                            "path": rel,
                            "row": i,
                            "date_utc": d,
                            "column": value_col,
                            "value": value,
                        },
                    )
                )
            continue
        out[d] += float(value)
    return dict(out)


def _pick_blob_month(common_dates: list[str], explicit_month: str | None) -> str | None:
    if explicit_month is not None:
        if explicit_month.count("-") != 1:
            return None
        return explicit_month

    if not common_dates:
        return None

    counts: dict[str, int] = defaultdict(int)
    for d in common_dates:
        m = _parse_month(d)
        if m is not None:
            counts[m] += 1

    if not counts:
        return None

    max_days = max(counts.values())
    candidate_months = sorted([m for m, c in counts.items() if c == max_days])
    return candidate_months[0]


def run_validation(
    *,
    mode: str,
    growthepie_csv: Path | None,
    onchain_csv: Path | None,
    l2beat_csv: Path | None,
    blobscan_csv: Path | None,
    onchain_blob_csv: Path | None,
    blob_month: str | None,
    top_k: int,
    out_json: Path,
    out_md: Path,
) -> int:
    failures: list[ValidationFailure] = []
    missing_inputs: list[str] = []
    effective_top_k = top_k
    if top_k <= 0:
        failures.append(
            ValidationFailure(
                check="config",
                message="invalid_top_k",
                details={"top_k": top_k, "required": "top_k >= 1"},
            )
        )
        effective_top_k = 1

    input_specs: list[dict[str, Any]] = [
        {"name": "growthepie", "path": growthepie_csv, "required": True},
        {"name": "onchain", "path": onchain_csv, "required": True},
        {"name": "l2beat", "path": l2beat_csv, "required": True},
        {"name": "blobscan", "path": blobscan_csv, "required": False},
        {"name": "onchain_blob", "path": onchain_blob_csv, "required": False},
    ]

    # Optional blob check requires both inputs or neither.
    if (blobscan_csv is None) ^ (onchain_blob_csv is None):
        failures.append(
            ValidationFailure(
                check="inputs",
                message="blob_check_requires_both_inputs",
                details={"blobscan_csv": _rel(blobscan_csv), "onchain_blob_csv": _rel(onchain_blob_csv)},
            )
        )
        _add_missing_input(missing_inputs, "blob_check_pair")

    input_rows: dict[str, list[dict[str, str]]] = {}
    input_fields: dict[str, list[str]] = {}

    for spec in input_specs:
        name = str(spec["name"])
        path = spec["path"]
        required = bool(spec["required"])

        if path is None:
            if required:
                failures.append(
                    ValidationFailure(
                        check="inputs",
                        message="missing_input_argument",
                        details={"source": name},
                    )
                )
                _add_missing_input(missing_inputs, f"arg:{name}")
            continue

        if not path.exists():
            failures.append(
                ValidationFailure(
                    check="inputs",
                    message="missing_input_file",
                    details={"source": name, "path": _rel(path)},
                )
            )
            if required:
                _add_missing_input(missing_inputs, _rel(path) or name)
            continue

        try:
            fieldnames, rows = _load_csv(path)
        except Exception as exc:
            failures.append(
                ValidationFailure(
                    check="inputs",
                    message="invalid_csv",
                    details={"source": name, "path": _rel(path), "error": str(exc)},
                )
            )
            if required:
                _add_missing_input(missing_inputs, _rel(path) or name)
            continue

        input_fields[name] = fieldnames
        input_rows[name] = rows

    # Required schema checks.
    if "growthepie" in input_fields:
        _validate_required_columns(
            source="growthepie",
            fieldnames=input_fields["growthepie"],
            required={"date_utc", "rollup_id", "l2_fees_eth", "rent_paid_eth"},
            failures=failures,
            missing_inputs=missing_inputs,
            input_path=growthepie_csv,
        )
    if "onchain" in input_fields:
        _validate_required_columns(
            source="onchain",
            fieldnames=input_fields["onchain"],
            required={"date_utc", "rollup_id", "rent_paid_eth"},
            failures=failures,
            missing_inputs=missing_inputs,
            input_path=onchain_csv,
        )
    if "l2beat" in input_fields:
        _validate_required_columns(
            source="l2beat",
            fieldnames=input_fields["l2beat"],
            required={"date_utc", "rollup_id", "total_cost_eth"},
            failures=failures,
            missing_inputs=missing_inputs,
            input_path=l2beat_csv,
        )

    # Schema checks for optional blob inputs (if provided).
    blobscan_blob_col: str | None = None
    onchain_blob_col: str | None = None
    if blobscan_csv is not None and "blobscan" in input_fields:
        _validate_required_columns(
            source="blobscan",
            fieldnames=input_fields["blobscan"],
            required={"date_utc"},
            failures=failures,
            missing_inputs=missing_inputs,
            input_path=blobscan_csv,
        )
        blobscan_blob_col = _detect_blob_column(input_fields["blobscan"], source="blobscan")
        if blobscan_blob_col is None:
            _add_missing_input(missing_inputs, _rel(blobscan_csv) or "blobscan")
            failures.append(
                ValidationFailure(
                    check="schema",
                    message="missing_blob_gas_column",
                    details={
                        "source": "blobscan",
                        "path": _rel(blobscan_csv),
                        "expected_any_of": ["l1_blob_gas_used", "blob_gas_used"],
                    },
                )
            )
    if onchain_blob_csv is not None and "onchain_blob" in input_fields:
        _validate_required_columns(
            source="onchain_blob",
            fieldnames=input_fields["onchain_blob"],
            required={"date_utc"},
            failures=failures,
            missing_inputs=missing_inputs,
            input_path=onchain_blob_csv,
        )
        onchain_blob_col = _detect_blob_column(input_fields["onchain_blob"], source="onchain_blob")
        if onchain_blob_col is None:
            _add_missing_input(missing_inputs, _rel(onchain_blob_csv) or "onchain_blob")
            failures.append(
                ValidationFailure(
                    check="schema",
                    message="missing_blob_gas_column",
                    details={
                        "source": "onchain_blob",
                        "path": _rel(onchain_blob_csv),
                        "expected_any_of": ["l1_blob_gas_used", "blob_gas_used", "rollup_blob_gas_used"],
                    },
                )
            )

    # Compute monthly reconciliation only when required inputs are present and parseable.
    monthly_records: list[dict[str, Any]] = []
    monthly_gt10_failures = 0
    monthly_le5 = 0
    monthly_5_10 = 0
    monthly_gt10 = 0
    top_rollups: list[str] = []

    growthepie_monthly: dict[tuple[str, str], float] = {}
    onchain_monthly: dict[tuple[str, str], float] = {}
    l2beat_monthly: dict[tuple[str, str], float] = {}
    unknown_rollups: dict[str, list[str]] = {"growthepie": [], "onchain": [], "l2beat": []}

    if all(k in input_rows for k in ["growthepie", "onchain", "l2beat"]):
        fees_by_rollup = _aggregate_rollup_fees_for_ranking(
            rows=input_rows["growthepie"],
            failures=failures,
            missing_inputs=missing_inputs,
            input_path=growthepie_csv,
        )
        top_rollups = _select_top_rollups(fees_by_rollup, effective_top_k)

        growthepie_monthly = _aggregate_monthly_rollup_metric(
            source="growthepie",
            rows=input_rows["growthepie"],
            value_col="rent_paid_eth",
            failures=failures,
            missing_inputs=missing_inputs,
            input_path=growthepie_csv,
        )
        onchain_monthly = _aggregate_monthly_rollup_metric(
            source="onchain",
            rows=input_rows["onchain"],
            value_col="rent_paid_eth",
            failures=failures,
            missing_inputs=missing_inputs,
            input_path=onchain_csv,
        )
        l2beat_monthly = _aggregate_monthly_rollup_metric(
            source="l2beat",
            rows=input_rows["l2beat"],
            value_col="total_cost_eth",
            failures=failures,
            missing_inputs=missing_inputs,
            input_path=l2beat_csv,
        )

        for source, rows in [("growthepie", input_rows["growthepie"]), ("onchain", input_rows["onchain"]), ("l2beat", input_rows["l2beat"])]:
            ids = sorted({str(r.get("rollup_id", "")).strip() for r in rows if _is_unknown_bucket(str(r.get("rollup_id", "")))})
            unknown_rollups[source] = [x for x in ids if x]

        months = sorted(
            {
                month
                for (month, rollup_id) in (set(growthepie_monthly) | set(onchain_monthly) | set(l2beat_monthly))
                if rollup_id in set(top_rollups)
            }
        )

        for month in months:
            for rollup_id in top_rollups:
                key = (month, rollup_id)
                g = growthepie_monthly.get(key)
                o = onchain_monthly.get(key)
                l = l2beat_monthly.get(key)

                if g is not None and o is not None:
                    pct = _safe_pct_delta(lhs=g, rhs=o, denom_ref=o)
                    band = "le_5pct" if pct <= MONTHLY_TOLERANCE_TARGET_LOW else ("le_10pct" if pct <= MONTHLY_TOLERANCE_TARGET_HIGH else "gt_10pct")
                    monthly_records.append(
                        {
                            "month_utc": month,
                            "rollup_id": rollup_id,
                            "source_pair": "growthepie_vs_onchain",
                            "growthepie_rent_eth": g,
                            "onchain_rent_eth": o,
                            "pct_delta": pct,
                            "band": band,
                        }
                    )
                    if pct <= MONTHLY_TOLERANCE_TARGET_LOW:
                        monthly_le5 += 1
                    elif pct <= MONTHLY_TOLERANCE_TARGET_HIGH:
                        monthly_5_10 += 1
                    else:
                        monthly_gt10 += 1
                        monthly_gt10_failures += 1
                        failures.append(
                            ValidationFailure(
                                check="monthly_reconciliation",
                                message="delta_gt_10pct",
                                details={
                                    "source_pair": "growthepie_vs_onchain",
                                    "month_utc": month,
                                    "rollup_id": rollup_id,
                                    "growthepie_rent_eth": g,
                                    "onchain_rent_eth": o,
                                    "pct_delta": pct,
                                    "tolerance_pct": MONTHLY_TOLERANCE_TARGET_HIGH,
                                },
                            )
                        )

                if l is not None and o is not None:
                    pct = _safe_pct_delta(lhs=l, rhs=o, denom_ref=o)
                    band = "le_5pct" if pct <= MONTHLY_TOLERANCE_TARGET_LOW else ("le_10pct" if pct <= MONTHLY_TOLERANCE_TARGET_HIGH else "gt_10pct")
                    monthly_records.append(
                        {
                            "month_utc": month,
                            "rollup_id": rollup_id,
                            "source_pair": "l2beat_vs_onchain",
                            "l2beat_total_cost_eth": l,
                            "onchain_rent_eth": o,
                            "pct_delta": pct,
                            "band": band,
                        }
                    )
                    if pct <= MONTHLY_TOLERANCE_TARGET_LOW:
                        monthly_le5 += 1
                    elif pct <= MONTHLY_TOLERANCE_TARGET_HIGH:
                        monthly_5_10 += 1
                    else:
                        monthly_gt10 += 1
                        monthly_gt10_failures += 1
                        failures.append(
                            ValidationFailure(
                                check="monthly_reconciliation",
                                message="delta_gt_10pct",
                                details={
                                    "source_pair": "l2beat_vs_onchain",
                                    "month_utc": month,
                                    "rollup_id": rollup_id,
                                    "l2beat_total_cost_eth": l,
                                    "onchain_rent_eth": o,
                                    "pct_delta": pct,
                                    "tolerance_pct": MONTHLY_TOLERANCE_TARGET_HIGH,
                                },
                            )
                        )

                # Informational only (non-authoritative pair), included for report completeness.
                if g is not None and l is not None:
                    monthly_records.append(
                        {
                            "month_utc": month,
                            "rollup_id": rollup_id,
                            "source_pair": "growthepie_vs_l2beat",
                            "growthepie_rent_eth": g,
                            "l2beat_total_cost_eth": l,
                            "pct_delta": _max_ref_pct_delta(lhs=g, rhs=l),
                        }
                    )

        if len([r for r in monthly_records if r.get("source_pair") in {"growthepie_vs_onchain", "l2beat_vs_onchain"}]) == 0:
            failures.append(
                ValidationFailure(
                    check="coverage",
                    message="no_monthly_overlap_for_required_pairs",
                    details={"top_rollups": top_rollups},
                )
            )

    # Blob gas check (optional, if both sources provided and parseable).
    blob_metrics: dict[str, Any] = {"status": "skipped"}
    if blobscan_csv is not None and onchain_blob_csv is not None and "blobscan" in input_rows and "onchain_blob" in input_rows:
        if blobscan_blob_col is None or onchain_blob_col is None:
            blob_metrics = {"status": "schema_error"}
        else:
            blobscan_daily = _aggregate_daily_metric(
                source="blobscan",
                rows=input_rows["blobscan"],
                value_col=blobscan_blob_col,
                failures=failures,
                missing_inputs=missing_inputs,
                input_path=blobscan_csv,
            )
            onchain_blob_daily = _aggregate_daily_metric(
                source="onchain_blob",
                rows=input_rows["onchain_blob"],
                value_col=onchain_blob_col,
                failures=failures,
                missing_inputs=missing_inputs,
                input_path=onchain_blob_csv,
            )

            common_dates = sorted(set(blobscan_daily.keys()) & set(onchain_blob_daily.keys()))
            selected_month = _pick_blob_month(common_dates, blob_month)

            if selected_month is None:
                failures.append(
                    ValidationFailure(
                        check="blob_gas_used_reconciliation",
                        message="missing_or_invalid_blob_month",
                        details={"blob_month": blob_month},
                    )
                )
                blob_metrics = {"status": "missing_or_invalid_blob_month", "blob_month": blob_month}
            else:
                selected_dates = [d for d in common_dates if d.startswith(selected_month + "-")]
                if not selected_dates:
                    failures.append(
                        ValidationFailure(
                            check="blob_gas_used_reconciliation",
                            message="no_overlap_for_selected_month",
                            details={"selected_month_utc": selected_month},
                        )
                    )
                    blob_metrics = {"status": "no_overlap_for_selected_month", "selected_month_utc": selected_month}
                else:
                    day_rows: list[dict[str, Any]] = []
                    days_gt_1pct = 0
                    for d in selected_dates:
                        b = blobscan_daily[d]
                        o = onchain_blob_daily[d]
                        pct = _safe_pct_delta(lhs=b, rhs=o, denom_ref=o)
                        day_rows.append(
                            {
                                "date_utc": d,
                                "blobscan_l1_blob_gas_used": b,
                                "onchain_l1_blob_gas_used": o,
                                "pct_delta": pct,
                            }
                        )
                        if pct > BLOB_GAS_TOLERANCE:
                            days_gt_1pct += 1
                            failures.append(
                                ValidationFailure(
                                    check="blob_gas_used_reconciliation",
                                    message="delta_gt_1pct",
                                    details={
                                        "date_utc": d,
                                        "selected_month_utc": selected_month,
                                        "blobscan_l1_blob_gas_used": b,
                                        "onchain_l1_blob_gas_used": o,
                                        "pct_delta": pct,
                                        "tolerance_pct": BLOB_GAS_TOLERANCE,
                                    },
                                )
                            )
                    blob_metrics = {
                        "status": "evaluated",
                        "selected_month_utc": selected_month,
                        "days_compared": len(day_rows),
                        "days_gt_1pct": days_gt_1pct,
                        "daily_rows": day_rows,
                    }

    inputs_for_report = []
    for spec in input_specs:
        path = spec["path"]
        required = bool(spec["required"])
        exists = bool(path.exists()) if isinstance(path, Path) else False
        inputs_for_report.append(
            {
                "name": spec["name"],
                "path": _rel(path),
                "exists": exists,
                "required": required,
            }
        )

    missing_inputs_sorted = sorted(missing_inputs)
    metrics: dict[str, Any] = {
        "mode": mode,
        "tolerances": {
            "monthly_target_pct_low": MONTHLY_TOLERANCE_TARGET_LOW,
            "monthly_target_pct_high": MONTHLY_TOLERANCE_TARGET_HIGH,
            "blob_gas_used_pct": BLOB_GAS_TOLERANCE,
        },
        "top_k": int(effective_top_k),
        "top_rollups_by_fees": top_rollups,
        "monthly_reconciliation_summary": {
            "records_total": len(monthly_records),
            "records_le_5pct": monthly_le5,
            "records_between_5pct_10pct": monthly_5_10,
            "records_gt_10pct": monthly_gt10,
            "gt_10pct_failure_rows": monthly_gt10_failures,
            "top_rollup_count": len(top_rollups),
        },
        "monthly_reconciliation": monthly_records,
        "unknown_unattributed_rollups": unknown_rollups,
        "blob_gas_used_check": blob_metrics,
        "missing_inputs": missing_inputs_sorted,
    }

    report = {
        "ok": (len(failures) == 0 and len(missing_inputs_sorted) == 0),
        "inputs": inputs_for_report,
        "metrics": metrics,
        "failures": [f.as_dict() for f in failures],
    }

    write_json(out_json, report)
    write_md(out_md, _build_md(report))
    return exit_code_for(ok=bool(report["ok"]), missing_inputs=missing_inputs_sorted)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="validate_cross_source.py")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--sample", action="store_true", help="Run deterministic validation using committed sample inputs.")
    mode.add_argument("--full", action="store_true", help="Run validation with explicit input arguments.")

    p.add_argument("--growthepie-csv", default=None, help="growthepie panel CSV path.")
    p.add_argument("--onchain-csv", default=None, help="On-chain rollup rent CSV path.")
    p.add_argument("--l2beat-csv", default=None, help="L2BEAT costs CSV path.")
    p.add_argument("--blobscan-csv", default=None, help="Optional Blobscan daily blob metrics CSV path.")
    p.add_argument("--onchain-blob-csv", default=None, help="Optional on-chain daily blob metrics CSV path.")
    p.add_argument("--blob-month", default=None, help="Optional month for blob check (YYYY-MM).")
    p.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Top-K rollups (by growthepie fees) for monthly checks.")
    p.add_argument("--out-json", default=str(DEFAULT_OUT_JSON), help="Output JSON path.")
    p.add_argument("--out-md", default=str(DEFAULT_OUT_MD), help="Output Markdown path.")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)

    if args.sample:
        growthepie_csv = Path(args.growthepie_csv) if args.growthepie_csv else SAMPLE_GROWTHEPIE_CSV
        onchain_csv = Path(args.onchain_csv) if args.onchain_csv else _first_existing(SAMPLE_ONCHAIN_CANDIDATES)
        l2beat_csv = Path(args.l2beat_csv) if args.l2beat_csv else _first_existing(SAMPLE_L2BEAT_CANDIDATES)
    else:
        growthepie_csv = Path(args.growthepie_csv) if args.growthepie_csv else None
        onchain_csv = Path(args.onchain_csv) if args.onchain_csv else None
        l2beat_csv = Path(args.l2beat_csv) if args.l2beat_csv else None

    blobscan_csv = Path(args.blobscan_csv) if args.blobscan_csv else None
    onchain_blob_csv = Path(args.onchain_blob_csv) if args.onchain_blob_csv else None

    return run_validation(
        mode="sample" if args.sample else "full",
        growthepie_csv=growthepie_csv,
        onchain_csv=onchain_csv,
        l2beat_csv=l2beat_csv,
        blobscan_csv=blobscan_csv,
        onchain_blob_csv=onchain_blob_csv,
        blob_month=args.blob_month,
        top_k=args.top_k,
        out_json=out_json,
        out_md=out_md,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
