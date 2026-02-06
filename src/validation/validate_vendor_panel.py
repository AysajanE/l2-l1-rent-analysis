from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.analysis.metrics_str import compute_daily_ecosystem_str, parse_optional_float  # noqa: E402
from src.validation.reporting import (  # noqa: E402
    ValidationFailure,
    exit_code_for,
    write_json,
    write_md,
)


SAMPLE_CSV = REPO_ROOT / "data" / "samples" / "growthepie" / "vendor_daily_rollup_panel_sample.csv"
DEFAULT_OUT_JSON = REPO_ROOT / "reports" / "validation" / "vendor_panel_validation.json"
DEFAULT_OUT_MD = REPO_ROOT / "reports" / "validation" / "vendor_panel_validation.md"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except Exception:
        return str(path)


def _load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("missing_header")
        rows = [dict(r) for r in reader]
        return list(reader.fieldnames), rows


def _vendor_identity_ok(*, fees: float, rent_paid: float, profit: float) -> bool:
    """Check profit ≈ fees − rent_paid using the protocol tolerance formula (ETH).

    Per docs/protocol.md (locked):
      abs(profit − (fees − rent_paid)) <= max(1e-9, 0.01 × max(abs(fees), abs(rent_paid), 1e-9))
    """
    err = abs(profit - (fees - rent_paid))
    tol = max(1e-9, 0.01 * max(abs(fees), abs(rent_paid), 1e-9))
    return err <= tol


def _build_md(report: dict[str, Any]) -> str:
    ok = bool(report.get("ok"))
    missing_inputs = report.get("missing_inputs") or []
    status = "PASS" if ok else ("MISSING INPUTS" if missing_inputs else "FAIL")

    lines: list[str] = []
    lines.append("# Vendor panel validation")
    lines.append("")
    lines.append(f"- Status: **{status}**")
    lines.append("")

    lines.append("## Inputs")
    for inp in report.get("inputs", []) or []:
        if isinstance(inp, dict):
            path = inp.get("path")
            exists = inp.get("exists")
            lines.append(f"- {path} (exists={exists})")
    lines.append("")

    metrics = report.get("metrics")
    if isinstance(metrics, dict) and metrics:
        lines.append("## Metrics")
        for k in sorted(metrics.keys()):
            lines.append(f"- {k}: {metrics[k]}")
        lines.append("")

    failures = report.get("failures") or []
    if failures:
        lines.append("## Failures")
        for f in failures[:50]:
            if isinstance(f, dict):
                lines.append(f"- [{f.get('check')}] {f.get('message')}")
        if len(failures) > 50:
            lines.append(f"- (truncated; total failures={len(failures)})")
        lines.append("")

    notes = report.get("notes") or []
    if notes:
        lines.append("## Next steps")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run_validation(*, input_csv: Path, out_json: Path, out_md: Path) -> int:
    failures: list[ValidationFailure] = []
    missing_inputs: list[str] = []

    if not input_csv.exists():
        missing_inputs.append(_rel(input_csv))
        failures.append(ValidationFailure(check="inputs", message="missing_input_csv", details={"path": _rel(input_csv)}))
        report = {
            "ok": False,
            "inputs": [{"path": _rel(input_csv), "exists": False}],
            "metrics": {},
            "failures": [f.as_dict() for f in failures],
            "missing_inputs": missing_inputs,
            "notes": [
                "Generate the committed sample via W1 growthepie ETL (T030), then rerun: python src/validation/validate_vendor_panel.py --sample",
            ],
        }
        write_json(out_json, report)
        write_md(out_md, _build_md(report))
        return exit_code_for(ok=False, missing_inputs=missing_inputs)

    try:
        fieldnames, rows = _load_csv(input_csv)
    except Exception as exc:
        missing_inputs.append(_rel(input_csv))
        failures.append(ValidationFailure(check="inputs", message="invalid_csv", details={"error": str(exc)}))
        report = {
            "ok": False,
            "inputs": [{"path": _rel(input_csv), "exists": True}],
            "metrics": {},
            "failures": [f.as_dict() for f in failures],
            "missing_inputs": missing_inputs,
        }
        write_json(out_json, report)
        write_md(out_md, _build_md(report))
        return exit_code_for(ok=False, missing_inputs=missing_inputs)

    required_cols = {"date_utc", "rollup_id", "l2_fees_eth", "rent_paid_eth"}
    missing_cols = sorted(c for c in required_cols if c not in set(fieldnames))
    if missing_cols:
        missing_inputs.append(_rel(input_csv))
        failures.append(
            ValidationFailure(
                check="schema",
                message="missing_required_columns",
                details={"missing_columns": missing_cols},
            )
        )

    # Row-level checks (cap collected failures for report compactness).
    negative_count = 0
    identity_fail_count = 0
    identity_checked = 0
    parsed_rows_for_str: list[dict[str, Any]] = []

    for i, row in enumerate(rows):
        date_utc = row.get("date_utc", "")
        rollup_id = row.get("rollup_id", "")

        l2_fees = parse_optional_float(row.get("l2_fees_eth"))
        rent_paid = parse_optional_float(row.get("rent_paid_eth"))
        profit = parse_optional_float(row.get("profit_eth"))

        # Non-negativity for fee/rent (profit may be negative: rent > fees).
        for col, v in [("l2_fees_eth", l2_fees), ("rent_paid_eth", rent_paid)]:
            if v is None:
                continue
            if v < 0:
                negative_count += 1
                if len(failures) < 50:
                    failures.append(
                        ValidationFailure(
                            check="non_negativity",
                            message="negative_value",
                            details={"row": i, "date_utc": date_utc, "rollup_id": rollup_id, "column": col, "value": v},
                        )
                    )

        # Identity check (only if profit/fees/rent present).
        if l2_fees is not None and rent_paid is not None and profit is not None:
            identity_checked += 1
            if not _vendor_identity_ok(fees=l2_fees, rent_paid=rent_paid, profit=profit):
                identity_fail_count += 1
                if len(failures) < 50:
                    failures.append(
                        ValidationFailure(
                            check="vendor_identity",
                            message="profit_not_close_to_fees_minus_rent",
                            details={"row": i, "date_utc": date_utc, "rollup_id": rollup_id},
                        )
                    )

        # Feed STR computation (missingness rule handled by metrics_str).
        parsed_rows_for_str.append(
            {
                "date_utc": date_utc,
                "rollup_id": rollup_id,
                "l2_fees_eth": row.get("l2_fees_eth"),
                "rent_paid_eth": row.get("rent_paid_eth"),
            }
        )

    # STR sanity.
    daily = compute_daily_ecosystem_str(parsed_rows_for_str)
    str_nonfinite_days = 0
    str_nan_on_positive_fee_days = 0
    finite_values: list[float] = []
    for d in daily:
        if d.l2_fees_eth_sum > 0:
            if math.isnan(d.str_value):
                str_nan_on_positive_fee_days += 1
            elif not math.isfinite(d.str_value):
                str_nonfinite_days += 1
        if math.isfinite(d.str_value):
            finite_values.append(d.str_value)

    if str_nan_on_positive_fee_days > 0:
        failures.append(
            ValidationFailure(
                check="str_sanity",
                message="str_nan_on_positive_fee_days",
                details={"count": str_nan_on_positive_fee_days},
            )
        )
    if str_nonfinite_days > 0:
        failures.append(
            ValidationFailure(
                check="str_sanity",
                message="str_nonfinite_days",
                details={"count": str_nonfinite_days},
            )
        )

    unique_rollups = {r.get("rollup_id", "") for r in rows if r.get("rollup_id")}
    unique_dates = {r.get("date_utc", "") for r in rows if r.get("date_utc")}
    date_min = min(unique_dates) if unique_dates else None
    date_max = max(unique_dates) if unique_dates else None

    metrics: dict[str, Any] = {
        "rows": len(rows),
        "unique_rollups": len(unique_rollups),
        "unique_dates": len(unique_dates),
        "date_min": date_min,
        "date_max": date_max,
        "negative_value_rows": negative_count,
        "vendor_identity_checked_rows": identity_checked,
        "vendor_identity_failed_rows": identity_fail_count,
        "daily_str_points": len(daily),
        "daily_str_min": (min(finite_values) if finite_values else None),
        "daily_str_max": (max(finite_values) if finite_values else None),
    }

    report = {
        "ok": (len(failures) == 0 and not missing_inputs),
        "inputs": [{"path": _rel(input_csv), "exists": True}],
        "metrics": metrics,
        "failures": [f.as_dict() for f in failures],
        "missing_inputs": missing_inputs,
    }
    if not report["ok"]:
        report["notes"] = [
            "If vendor identity fails, confirm growthepie metric keys/units and re-snapshot master.json for provenance.",
            "If STR sanity fails, inspect rows with missing/zero fees and confirm missingness is represented by row omission (not null coercion).",
        ]

    write_json(out_json, report)
    write_md(out_md, _build_md(report))
    return exit_code_for(ok=bool(report["ok"]), missing_inputs=missing_inputs)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="validate_vendor_panel.py")
    p.add_argument("--sample", action="store_true", help="Validate the committed growthepie sample panel (default).")
    p.add_argument("--input-csv", default=None, help="Optional override input CSV path.")
    p.add_argument("--out-json", default=str(DEFAULT_OUT_JSON), help="Output JSON path.")
    p.add_argument("--out-md", default=str(DEFAULT_OUT_MD), help="Output Markdown path.")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    input_csv = Path(args.input_csv) if args.input_csv else SAMPLE_CSV
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    return run_validation(input_csv=input_csv, out_json=out_json, out_md=out_md)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
