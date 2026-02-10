from __future__ import annotations

"""Rent decomposition shares over time (deterministic; offline).

Inputs (sample mode, default):
- `data/samples/panels/daily_rollup_panel_v2_sample.csv`

Inputs (optional full mode):
- `--panel <path>` pointing to a contract-v2 daily rollup panel CSV
  (see `contracts/schemas/panel_schema_str_v2.yaml`)

Outputs (sample mode stable names):
- `reports/tables/rent_decomposition_sample.csv`
- `reports/figures/rent_decomposition_sample.svg`
- `reports/tables/rent_decomposition_sample_run.json`

How to run:
- Sample (default):
  `python src/analysis/plot_rent_decomposition.py`
- Explicit sample:
  `python src/analysis/plot_rent_decomposition.py --sample`
- Full (example):
  `python src/analysis/plot_rent_decomposition.py --panel data/processed/panels/daily_rollup_panel_v2.csv --tag full`
"""

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DENCUN_DATE_UTC = date(2024, 3, 13)
TASK_ID = "T101"
CONTRACT_REFERENCES = [
    "contracts/schemas/panel_schema_str_v2.yaml",
    "docs/protocol.md",
]

SUMMARY_COLUMNS = [
    "date_utc",
    "is_post_dencun",
    "included_rollup_days",
    "l2_fees_eth_sum",
    "rent_paid_eth_sum",
    "rent_base_fee_burn_eth_sum",
    "rent_blob_fee_burn_eth_sum",
    "rent_priority_fee_eth_sum",
    "rent_unattributed_eth_sum",
    "rent_execution_eth_sum",
    "rent_burn_eth_sum",
    "ecosystem_str",
    "share_base_burn_of_rent",
    "share_blob_burn_of_rent",
    "share_execution_of_rent",
    "share_burn_of_rent",
    "share_priority_fee_of_rent",
    "share_unattributed_of_rent",
]

REQUIRED_COLUMNS = {
    "date_utc",
    "rollup_id",
    "l2_fees_eth",
    "rent_paid_eth",
    "rent_base_fee_burn_eth",
    "rent_blob_fee_burn_eth",
    "rent_priority_fee_eth",
}

Row = dict[str, str]


def _repo_root() -> Path:
    return REPO_ROOT


def _ensure_within_repo(root: Path, target: Path) -> Path:
    try:
        return target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"path must be inside repo root: {root} (got {target})") from exc


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_sha(root: Path) -> str | None:
    try:
        run = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    sha = run.stdout.strip()
    return sha or None


def _require_str(row: Row, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise SystemExit(f"Missing required field {key!r}")
    return value.strip()


def _parse_date_utc(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid date_utc (expected YYYY-MM-DD): {value!r}") from exc


def _parse_float_required(row: Row, key: str) -> float:
    raw = _require_str(row, key)
    try:
        value = float(raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid float for {key!r}: {raw!r}") from exc
    if not math.isfinite(value):
        raise SystemExit(f"Non-finite value for {key!r}: {raw!r}")
    return value


def _parse_optional_float(row: Row, key: str) -> tuple[float, bool]:
    value = row.get(key)
    if value is None:
        raise SystemExit(f"Missing required column {key!r} in row")
    if not isinstance(value, str):
        raise SystemExit(f"Invalid type for {key!r}: expected string, got {type(value)}")
    stripped = value.strip()
    if stripped == "":
        return 0.0, False
    try:
        parsed = float(stripped)
    except ValueError as exc:
        raise SystemExit(f"Invalid float for {key!r}: {stripped!r}") from exc
    if not math.isfinite(parsed):
        raise SystemExit(f"Non-finite value for {key!r}: {stripped!r}")
    return parsed, True


def load_panel_csv(path: Path) -> tuple[list[str], list[Row]]:
    with path.open("r", encoding="utf-8", newline="") as file_obj:
        raw_lines = file_obj.readlines()
    lines = [ln for ln in raw_lines if not ln.lstrip().startswith("#") and ln.strip() != ""]
    if not lines:
        raise SystemExit(f"Empty CSV (after stripping comments): {path}")

    reader = csv.DictReader(lines)
    if reader.fieldnames is None:
        raise SystemExit(f"Missing CSV header: {path}")
    fieldnames = list(reader.fieldnames)
    rows: list[Row] = [dict(row) for row in reader]
    return fieldnames, rows


def _validate_required_columns(fieldnames: list[str]) -> None:
    missing = sorted(col for col in REQUIRED_COLUMNS if col not in set(fieldnames))
    if missing:
        raise SystemExit(f"Input panel is missing required columns: {missing}")


@dataclass
class DailyAccumulator:
    l2_fees_eth_sum: float = 0.0
    rent_paid_eth_sum: float = 0.0
    rent_base_fee_burn_eth_sum: float = 0.0
    rent_blob_fee_burn_eth_sum: float = 0.0
    rent_priority_fee_eth_sum: float = 0.0
    rent_unattributed_eth_sum: float = 0.0
    rent_execution_eth_sum: float = 0.0
    included_rollup_days: int = 0


@dataclass(frozen=True)
class DecompositionResult:
    rows: list[dict[str, object]]
    coverage: dict[str, int]


def compute_daily_decomposition(rows: Iterable[Row]) -> DecompositionResult:
    per_day: dict[str, DailyAccumulator] = {}
    coverage = {
        "rows_total": 0,
        "rows_with_base_fee_burn_eth": 0,
        "rows_with_blob_fee_burn_eth": 0,
        "rows_with_priority_fee_eth": 0,
    }
    eps = 1e-9

    for row in rows:
        coverage["rows_total"] += 1

        date_str = _require_str(row, "date_utc")
        _parse_date_utc(date_str)
        rollup_id = _require_str(row, "rollup_id")

        fees = _parse_float_required(row, "l2_fees_eth")
        rent = _parse_float_required(row, "rent_paid_eth")
        if fees < 0 or rent < 0:
            raise SystemExit(f"Negative values not allowed: {date_str=} {rollup_id=} {fees=} {rent=}")

        base_burn, base_present = _parse_optional_float(row, "rent_base_fee_burn_eth")
        blob_burn, blob_present = _parse_optional_float(row, "rent_blob_fee_burn_eth")
        priority_fee, priority_present = _parse_optional_float(row, "rent_priority_fee_eth")

        if base_present:
            coverage["rows_with_base_fee_burn_eth"] += 1
        if blob_present:
            coverage["rows_with_blob_fee_burn_eth"] += 1
        if priority_present:
            coverage["rows_with_priority_fee_eth"] += 1

        if base_burn < 0 or blob_burn < 0 or priority_fee < 0:
            raise SystemExit(
                "Negative decomposition component not allowed: "
                f"{date_str=} {rollup_id=} {base_burn=} {blob_burn=} {priority_fee=}"
            )

        known_component_sum = base_burn + blob_burn + priority_fee
        residual = rent - known_component_sum
        if residual < -eps:
            raise SystemExit(
                "Decomposition components exceed rent_paid_eth by more than tolerance: "
                f"{date_str=} {rollup_id=} rent={rent} known_sum={known_component_sum}"
            )
        if residual < 0:
            residual = 0.0

        execution = rent - blob_burn
        if execution < -eps:
            raise SystemExit(
                "rent_execution_eth would be negative beyond tolerance: "
                f"{date_str=} {rollup_id=} rent={rent} blob_burn={blob_burn}"
            )
        if execution < 0:
            execution = 0.0

        acc = per_day.get(date_str)
        if acc is None:
            acc = DailyAccumulator()
            per_day[date_str] = acc

        acc.l2_fees_eth_sum += fees
        acc.rent_paid_eth_sum += rent
        acc.rent_base_fee_burn_eth_sum += base_burn
        acc.rent_blob_fee_burn_eth_sum += blob_burn
        acc.rent_priority_fee_eth_sum += priority_fee
        acc.rent_unattributed_eth_sum += residual
        acc.rent_execution_eth_sum += execution
        acc.included_rollup_days += 1

    out_rows: list[dict[str, object]] = []
    for date_str in sorted(per_day.keys()):
        d = _parse_date_utc(date_str)
        acc = per_day[date_str]
        rent_sum = acc.rent_paid_eth_sum
        fees_sum = acc.l2_fees_eth_sum

        ecosystem_str = math.nan if fees_sum == 0 else (rent_sum / fees_sum)
        share_base = math.nan if rent_sum == 0 else (acc.rent_base_fee_burn_eth_sum / rent_sum)
        share_blob = math.nan if rent_sum == 0 else (acc.rent_blob_fee_burn_eth_sum / rent_sum)
        share_execution = math.nan if rent_sum == 0 else (acc.rent_execution_eth_sum / rent_sum)
        burn_sum = acc.rent_base_fee_burn_eth_sum + acc.rent_blob_fee_burn_eth_sum
        share_burn = math.nan if rent_sum == 0 else (burn_sum / rent_sum)
        share_priority = math.nan if rent_sum == 0 else (acc.rent_priority_fee_eth_sum / rent_sum)
        share_unattributed = math.nan if rent_sum == 0 else (acc.rent_unattributed_eth_sum / rent_sum)

        out_rows.append(
            {
                "date_utc": date_str,
                "is_post_dencun": "true" if d >= DENCUN_DATE_UTC else "false",
                "included_rollup_days": acc.included_rollup_days,
                "l2_fees_eth_sum": f"{acc.l2_fees_eth_sum:.8f}",
                "rent_paid_eth_sum": f"{acc.rent_paid_eth_sum:.8f}",
                "rent_base_fee_burn_eth_sum": f"{acc.rent_base_fee_burn_eth_sum:.8f}",
                "rent_blob_fee_burn_eth_sum": f"{acc.rent_blob_fee_burn_eth_sum:.8f}",
                "rent_priority_fee_eth_sum": f"{acc.rent_priority_fee_eth_sum:.8f}",
                "rent_unattributed_eth_sum": f"{acc.rent_unattributed_eth_sum:.8f}",
                "rent_execution_eth_sum": f"{acc.rent_execution_eth_sum:.8f}",
                "rent_burn_eth_sum": f"{burn_sum:.8f}",
                "ecosystem_str": f"{ecosystem_str:.10f}",
                "share_base_burn_of_rent": f"{share_base:.10f}",
                "share_blob_burn_of_rent": f"{share_blob:.10f}",
                "share_execution_of_rent": f"{share_execution:.10f}",
                "share_burn_of_rent": f"{share_burn:.10f}",
                "share_priority_fee_of_rent": f"{share_priority:.10f}",
                "share_unattributed_of_rent": f"{share_unattributed:.10f}",
            }
        )

    return DecompositionResult(rows=out_rows, coverage=coverage)


def _write_summary_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for i, row in enumerate(rows):
        missing = [col for col in SUMMARY_COLUMNS if col not in row]
        if missing:
            raise SystemExit(f"Output schema mismatch at row {i}: missing columns {missing}")
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=SUMMARY_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in SUMMARY_COLUMNS})


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _segment_points(xs: list[int], ys: list[float]) -> list[list[tuple[int, float]]]:
    if len(xs) != len(ys):
        raise ValueError("xs/ys length mismatch")
    segments: list[list[tuple[int, float]]] = []
    current: list[tuple[int, float]] = []
    for x, y in zip(xs, ys, strict=True):
        if not math.isfinite(y):
            if current:
                segments.append(current)
                current = []
            continue
        current.append((x, y))
    if current:
        segments.append(current)
    return segments


@dataclass(frozen=True)
class ChartSeries:
    label: str
    color: str
    values: list[float]


def _series_polylines(
    *,
    series: ChartSeries,
    xs: list[int],
    x_px: Any,
    y_px: Any,
) -> list[str]:
    out: list[str] = []
    for segment in _segment_points(xs, series.values):
        if len(segment) < 2:
            continue
        points = " ".join(f"{x_px(x):.2f},{y_px(y):.2f}" for x, y in segment)
        out.append(f'<polyline fill="none" stroke="{series.color}" stroke-width="2.5" points="{points}" />')
    return out


def _choose_tick_indices(count: int, max_ticks: int) -> list[int]:
    if count <= 0:
        return []
    if count == 1:
        return [0]
    ticks = max(2, min(max_ticks, count))
    out = sorted({int(round((count - 1) * i / float(ticks - 1))) for i in range(ticks)})
    if out[0] != 0:
        out = [0, *out]
    if out[-1] != count - 1:
        out = [*out, count - 1]
    return sorted(set(out))


def _svg_share_chart(
    *,
    width: int,
    height: int,
    dates: list[str],
    series: list[ChartSeries],
    dencun_x: int | None,
    title: str,
    subtitle: str,
) -> str:
    if not dates:
        raise ValueError("empty chart dates")
    xs = list(range(len(dates)))
    for item in series:
        if len(item.values) != len(xs):
            raise ValueError("series length mismatch")

    margin_left = 68
    margin_right = 18
    margin_top = 62
    margin_bottom = 58
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    x_min = min(xs)
    x_max = max(xs)
    if x_min == x_max:
        x_min -= 1
        x_max += 1

    y0 = 0.0
    y1 = 1.0

    def x_px(x: int) -> float:
        return margin_left + plot_w * ((x - x_min) / float(x_max - x_min))

    def y_px(y: float) -> float:
        return margin_top + plot_h * (1.0 - ((y - y0) / float(y1 - y0)))

    y_tick_values = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    y_tick_elems: list[str] = []
    for tick in y_tick_values:
        yp = y_px(tick)
        y_tick_elems.append(
            f'<line x1="{margin_left}" y1="{yp:.2f}" x2="{margin_left + plot_w}" y2="{yp:.2f}" '
            'stroke="#dddddd" stroke-width="1" />'
        )
        y_tick_elems.append(
            f'<line x1="{margin_left-6}" y1="{yp:.2f}" x2="{margin_left}" y2="{yp:.2f}" stroke="#333333" />'
        )
        y_tick_elems.append(
            f'<text x="{margin_left-9}" y="{yp+4:.2f}" font-size="11" text-anchor="end" fill="#111111">{tick:.1f}</text>'
        )

    x_tick_elems: list[str] = []
    for idx in _choose_tick_indices(len(dates), 7):
        xp = x_px(idx)
        x_tick_elems.append(
            f'<line x1="{xp:.2f}" y1="{margin_top + plot_h}" x2="{xp:.2f}" y2="{margin_top + plot_h + 5}" stroke="#333333" />'
        )
        x_tick_elems.append(
            f'<text x="{xp:.2f}" y="{margin_top + plot_h + 20}" font-size="10" text-anchor="middle" fill="#111111">{dates[idx]}</text>'
        )

    dencun_line = ""
    if dencun_x is not None and x_min <= dencun_x <= x_max:
        xp = x_px(dencun_x)
        dencun_line = (
            f'<line x1="{xp:.2f}" y1="{margin_top}" x2="{xp:.2f}" y2="{margin_top + plot_h}" '
            'stroke="#b45309" stroke-width="2" stroke-dasharray="6 6" />'
        )

    legend_elems: list[str] = []
    legend_x = margin_left
    legend_y = 36
    for item in series:
        legend_elems.append(f'<rect x="{legend_x}" y="{legend_y-9}" width="10" height="10" fill="{item.color}" />')
        legend_elems.append(
            f'<text x="{legend_x+14}" y="{legend_y}" font-size="12" fill="#111111">{item.label}</text>'
        )
        legend_x += 210

    line_elems: list[str] = []
    for item in series:
        line_elems.extend(_series_polylines(series=item, xs=xs, x_px=x_px, y_px=y_px))

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect x="0" y="0" width="100%" height="100%" fill="white" />',
            f'<text x="{margin_left}" y="18" font-size="14" fill="#111111">{title}</text>',
            f'<text x="{margin_left}" y="54" font-size="11" fill="#4b5563">{subtitle}</text>',
            f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#111111" />',
            f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" stroke="#111111" />',
            *y_tick_elems,
            *x_tick_elems,
            *legend_elems,
            dencun_line,
            *line_elems,
            "</svg>",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plot_rent_decomposition.py")
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use the committed sample v2 panel (default when --panel is omitted)",
    )
    parser.add_argument("--panel", default=None, help="Path to a daily_rollup_panel v2 CSV")
    parser.add_argument("--tag", default=None, help="Output tag suffix (default: sample/full)")
    return parser


def _resolve_panel(*, root: Path, args: argparse.Namespace) -> tuple[Path, str]:
    if args.sample and args.panel is not None:
        raise SystemExit("Use either --sample or --panel, not both")

    if args.panel is not None:
        panel_arg = Path(args.panel)
        panel_abs = panel_arg if panel_arg.is_absolute() else (root / panel_arg)
        tag = str(args.tag or "full")
        return panel_abs, tag

    panel_abs = root / "data/samples/panels/daily_rollup_panel_v2_sample.csv"
    tag = str(args.tag or "sample")
    return panel_abs, tag


def _output_paths(*, root: Path, tag: str) -> tuple[Path, Path, Path]:
    if tag == "sample":
        out_csv = root / "reports/tables/rent_decomposition_sample.csv"
        out_svg = root / "reports/figures/rent_decomposition_sample.svg"
        out_run = root / "reports/tables/rent_decomposition_sample_run.json"
        return out_csv, out_svg, out_run

    out_csv = root / f"reports/tables/rent_decomposition_{tag}.csv"
    out_svg = root / f"reports/figures/rent_decomposition_{tag}.svg"
    out_run = root / f"reports/tables/rent_decomposition_{tag}_run.json"
    return out_csv, out_svg, out_run


def main(argv: list[str]) -> None:
    root = _repo_root()
    args = build_parser().parse_args(argv[1:])

    panel_abs, tag = _resolve_panel(root=root, args=args)
    if not panel_abs.exists():
        raise SystemExit(f"panel not found: {panel_abs}")

    panel_rel = str(_ensure_within_repo(root, panel_abs.resolve()))
    panel_sha = _sha256_file(panel_abs)

    out_csv, out_svg, out_run = _output_paths(root=root, tag=tag)

    fieldnames, rows = load_panel_csv(panel_abs)
    _validate_required_columns(fieldnames)
    decomposition = compute_daily_decomposition(rows)

    _write_summary_csv(out_csv, decomposition.rows)

    dates = [str(row["date_utc"]) for row in decomposition.rows]
    dencun_idx = next((i for i, d in enumerate(dates) if _parse_date_utc(d) >= DENCUN_DATE_UTC), None)
    svg = _svg_share_chart(
        width=1000,
        height=440,
        dates=dates,
        series=[
            ChartSeries(
                label="base burn share",
                color="#059669",
                values=[float(row["share_base_burn_of_rent"]) for row in decomposition.rows],
            ),
            ChartSeries(
                label="blob burn share",
                color="#2563eb",
                values=[float(row["share_blob_burn_of_rent"]) for row in decomposition.rows],
            ),
            ChartSeries(
                label="priority fee share",
                color="#dc2626",
                values=[float(row["share_priority_fee_of_rent"]) for row in decomposition.rows],
            ),
            ChartSeries(
                label="unattributed share",
                color="#6b7280",
                values=[float(row["share_unattributed_of_rent"]) for row in decomposition.rows],
            ),
        ],
        dencun_x=dencun_idx,
        title=f"Daily rent decomposition shares — {tag}",
        subtitle=(
            "Shares of rent_paid_eth (base burn, blob burn, priority fees, residual); "
            "Dencun boundary marked (2024-03-13 UTC)."
        ),
    )
    _write_text(out_svg, svg)

    now = datetime.now(timezone.utc).isoformat()
    run_manifest: dict[str, Any] = {
        "task_id": TASK_ID,
        "timestamp_utc": now,
        "script_path": str(_ensure_within_repo(root, Path(__file__).resolve())),
        "git_commit": _git_sha(root),
        "command": " ".join(json.dumps(token) for token in sys.argv),
        "contract_references": CONTRACT_REFERENCES,
        "parameters": {
            "tag": tag,
            "dencun_date_utc": DENCUN_DATE_UTC.isoformat(),
            "unattributed_definition": "rent_paid_eth - (rent_base_fee_burn_eth + rent_blob_fee_burn_eth + rent_priority_fee_eth)",
            "burn_definition": "rent_base_fee_burn_eth + rent_blob_fee_burn_eth",
            "execution_definition": "rent_paid_eth - rent_blob_fee_burn_eth",
        },
        "input_schema_checks": {
            "required_columns": sorted(REQUIRED_COLUMNS),
            "input_columns": fieldnames,
        },
        "coverage": decomposition.coverage,
        "inputs": [
            {"path": panel_rel, "sha256": panel_sha, "bytes": panel_abs.stat().st_size},
        ],
        "outputs": [],
    }
    run_manifest["outputs"] = [
        {"path": str(_ensure_within_repo(root, out_csv)), "sha256": _sha256_file(out_csv), "bytes": out_csv.stat().st_size},
        {"path": str(_ensure_within_repo(root, out_svg)), "sha256": _sha256_file(out_svg), "bytes": out_svg.stat().st_size},
    ]

    out_run.parent.mkdir(parents=True, exist_ok=True)
    out_run.write_text(json.dumps(run_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "tag": tag,
                "outputs": [str(out_csv), str(out_svg), str(out_run)],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main(sys.argv)
