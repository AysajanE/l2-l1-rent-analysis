from __future__ import annotations

"""Blob fee at-minimum/floor-binding linkage to ecosystem STR (deterministic).

Inputs (sample mode; default):
- `data/samples/panels/daily_rollup_panel_v2_sample.csv`

Inputs (full mode):
- `--panel <path>` pointing to a contract-v2 daily rollup panel CSV
  (see `contracts/schemas/panel_schema_str_v2.yaml`)

Outputs (stable names):
- `reports/tables/blob_floor_binding_str_link_<tag>.csv`
- `reports/figures/blob_floor_binding_str_link_<tag>.svg`
- `reports/tables/blob_floor_binding_str_link_<tag>_run.json`
  - Traceability: timestamp, command, git SHA (if available), and input/output hashes.

How to run:
- Sample (default):
  `python src/analysis/blob_floor_binding_str_link.py`
  or `python src/analysis/blob_floor_binding_str_link.py --sample`
- Full (example):
  `python src/analysis/blob_floor_binding_str_link.py --panel data/processed/panels/daily_rollup_panel_v2.csv --tag full`
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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Locked protocol constants (docs/protocol.md).
DENCUN_DATE_UTC = date(2024, 3, 13)
AT_MIN_MULTIPLIER_NUM = 105
AT_MIN_MULTIPLIER_DEN = 100
FLOOR_BINDING_MIN_RUN_DAYS = 7
WEI_PER_GWEI = 1_000_000_000


OUTPUT_COLUMNS = [
    "date_utc",
    "ecosystem_str",
    "l2_fees_eth_sum",
    "rent_paid_eth_sum",
    "included_rollup_days",
    "l1_blob_base_fee_wei",
    "is_post_dencun",
    "at_minimum_threshold_wei",
    "is_at_minimum_5pct",
    "at_minimum_run_id",
    "at_minimum_run_length_days",
    "is_floor_binding_regime_7d",
]


Row = dict[str, str]


@dataclass
class DailyAggregate:
    date_utc: str
    date_obj: date
    l2_fees_eth_sum: float
    rent_paid_eth_sum: float
    ecosystem_str: float
    included_rollup_days: int
    l1_blob_base_fee_wei: int | None
    is_post_dencun: bool
    is_at_minimum_5pct: int = 0
    at_minimum_run_id: int | None = None
    at_minimum_run_length_days: int = 0
    is_floor_binding_regime_7d: int = 0


def _repo_root() -> Path:
    return REPO_ROOT


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_within_repo(root: Path, target: Path) -> Path:
    try:
        return target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"path must be inside repo root: {root} (got {target})") from exc


def _git_sha(root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    sha = r.stdout.strip()
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
    s = _require_str(row, key)
    try:
        value = float(s)
    except ValueError as exc:
        raise SystemExit(f"Invalid float for {key!r}: {s!r}") from exc
    if not math.isfinite(value):
        raise SystemExit(f"Non-finite value for {key!r}: {s!r}")
    return value


def _parse_int_optional(row: Row, key: str) -> int | None:
    raw = row.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise SystemExit(f"Invalid type for {key!r}: expected string, got {type(raw)}")
    s = raw.strip()
    if s == "":
        return None
    try:
        return int(s)
    except ValueError as exc:
        raise SystemExit(f"Invalid int for {key!r}: {s!r}") from exc


def _mean(values: list[float]) -> float:
    if not values:
        return math.nan
    return sum(values) / float(len(values))


def _pearson_corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys):
        raise ValueError("pearson inputs length mismatch")
    n = len(xs)
    if n < 2:
        return math.nan
    mx = _mean(xs)
    my = _mean(ys)
    if not math.isfinite(mx) or not math.isfinite(my):
        return math.nan
    cov = 0.0
    vx = 0.0
    vy = 0.0
    for x, y in zip(xs, ys, strict=True):
        dx = x - mx
        dy = y - my
        cov += dx * dy
        vx += dx * dx
        vy += dy * dy
    if vx <= 0.0 or vy <= 0.0:
        return math.nan
    return cov / math.sqrt(vx * vy)


def load_panel_csv(path: Path) -> tuple[list[str], list[Row]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        raw_lines = f.readlines()
    lines = [ln for ln in raw_lines if not ln.lstrip().startswith("#") and ln.strip() != ""]
    if not lines:
        raise SystemExit(f"Empty CSV (after stripping comments): {path}")
    reader = csv.DictReader(lines)
    if reader.fieldnames is None:
        raise SystemExit(f"Missing CSV header: {path}")
    return list(reader.fieldnames), [dict(r) for r in reader]


def _validate_input_columns(fieldnames: list[str]) -> None:
    required = {
        "date_utc",
        "rollup_id",
        "l2_fees_eth",
        "rent_paid_eth",
        "l1_blob_base_fee_wei",
    }
    missing = sorted(col for col in required if col not in set(fieldnames))
    if missing:
        raise SystemExit(f"Input panel is missing required columns: {missing}")


def compute_daily_series(rows: Iterable[Row]) -> list[DailyAggregate]:
    per_day: dict[str, dict[str, Any]] = {}

    for row in rows:
        date_str = _require_str(row, "date_utc")
        rollup_id = _require_str(row, "rollup_id")
        _parse_date_utc(date_str)

        fees = _parse_float_required(row, "l2_fees_eth")
        rent = _parse_float_required(row, "rent_paid_eth")
        if fees < 0 or rent < 0:
            raise SystemExit(f"Negative values not allowed: {date_str=} {rollup_id=} {fees=} {rent=}")

        blob_fee_wei = _parse_int_optional(row, "l1_blob_base_fee_wei")
        if blob_fee_wei is not None and blob_fee_wei < 0:
            raise SystemExit(f"Negative l1_blob_base_fee_wei not allowed: {date_str=} {blob_fee_wei=}")

        bucket = per_day.get(date_str)
        if bucket is None:
            bucket = {
                "l2_fees_eth_sum": 0.0,
                "rent_paid_eth_sum": 0.0,
                "included_rollup_days": 0,
                "l1_blob_base_fee_wei": blob_fee_wei,
            }
            per_day[date_str] = bucket
        else:
            existing_blob_fee = bucket["l1_blob_base_fee_wei"]
            if existing_blob_fee is None and blob_fee_wei is None:
                pass
            elif existing_blob_fee is None or blob_fee_wei is None:
                raise SystemExit(f"Inconsistent null/non-null l1_blob_base_fee_wei within date: {date_str=}")
            elif int(existing_blob_fee) != int(blob_fee_wei):
                raise SystemExit(f"Inconsistent l1_blob_base_fee_wei within date: {date_str=}")

        bucket["l2_fees_eth_sum"] = float(bucket["l2_fees_eth_sum"]) + float(fees)
        bucket["rent_paid_eth_sum"] = float(bucket["rent_paid_eth_sum"]) + float(rent)
        bucket["included_rollup_days"] = int(bucket["included_rollup_days"]) + 1

    daily: list[DailyAggregate] = []
    for date_str in sorted(per_day.keys()):
        d = _parse_date_utc(date_str)
        b = per_day[date_str]
        fees_sum = float(b["l2_fees_eth_sum"])
        rent_sum = float(b["rent_paid_eth_sum"])
        ecosystem_str = math.nan if fees_sum == 0 else (rent_sum / fees_sum)
        daily.append(
            DailyAggregate(
                date_utc=date_str,
                date_obj=d,
                l2_fees_eth_sum=fees_sum,
                rent_paid_eth_sum=rent_sum,
                ecosystem_str=ecosystem_str,
                included_rollup_days=int(b["included_rollup_days"]),
                l1_blob_base_fee_wei=(int(b["l1_blob_base_fee_wei"]) if b["l1_blob_base_fee_wei"] is not None else None),
                is_post_dencun=(d >= DENCUN_DATE_UTC),
            )
        )
    return daily


def apply_at_minimum_and_floor_binding(daily: list[DailyAggregate]) -> tuple[int, int]:
    post_blob_fees: list[int] = []
    for day in daily:
        if not day.is_post_dencun:
            continue
        if day.l1_blob_base_fee_wei is None:
            raise SystemExit(f"Missing required post-Dencun field l1_blob_base_fee_wei: {day.date_utc=}")
        post_blob_fees.append(day.l1_blob_base_fee_wei)

    if not post_blob_fees:
        raise SystemExit("No post-Dencun rows with blob fee data were found")

    min_blob_fee_wei = min(post_blob_fees)
    threshold_wei = (min_blob_fee_wei * AT_MIN_MULTIPLIER_NUM) // AT_MIN_MULTIPLIER_DEN

    for day in daily:
        if day.is_post_dencun and day.l1_blob_base_fee_wei is not None and day.l1_blob_base_fee_wei <= threshold_wei:
            day.is_at_minimum_5pct = 1

    runs: list[list[int]] = []
    current: list[int] = []
    for idx, day in enumerate(daily):
        if day.is_post_dencun and day.is_at_minimum_5pct == 1:
            if not current:
                current = [idx]
            else:
                prev_day = daily[current[-1]]
                if day.date_obj - prev_day.date_obj == timedelta(days=1):
                    current.append(idx)
                else:
                    runs.append(current)
                    current = [idx]
        else:
            if current:
                runs.append(current)
                current = []
    if current:
        runs.append(current)

    run_id = 1
    for run_indices in runs:
        run_len = len(run_indices)
        for idx in run_indices:
            daily[idx].at_minimum_run_id = run_id
            daily[idx].at_minimum_run_length_days = run_len
            if run_len >= FLOOR_BINDING_MIN_RUN_DAYS:
                daily[idx].is_floor_binding_regime_7d = 1
        run_id += 1

    return min_blob_fee_wei, threshold_wei


def _validate_output_rows(rows: list[dict[str, object]]) -> None:
    if not rows:
        raise SystemExit("Output series is empty")
    required = set(OUTPUT_COLUMNS)
    for i, row in enumerate(rows, start=1):
        keys = set(row.keys())
        missing = sorted(required - keys)
        extra = sorted(keys - required)
        if missing or extra:
            raise SystemExit(f"Output schema mismatch at row {i}: missing={missing} extra={extra}")


def build_output_rows(daily: list[DailyAggregate], threshold_wei: int) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for day in daily:
        out.append(
            {
                "date_utc": day.date_utc,
                "ecosystem_str": (f"{day.ecosystem_str:.10f}" if math.isfinite(day.ecosystem_str) else ""),
                "l2_fees_eth_sum": f"{day.l2_fees_eth_sum:.8f}",
                "rent_paid_eth_sum": f"{day.rent_paid_eth_sum:.8f}",
                "included_rollup_days": day.included_rollup_days,
                "l1_blob_base_fee_wei": (day.l1_blob_base_fee_wei if day.l1_blob_base_fee_wei is not None else ""),
                "is_post_dencun": (1 if day.is_post_dencun else 0),
                "at_minimum_threshold_wei": (threshold_wei if day.is_post_dencun else ""),
                "is_at_minimum_5pct": day.is_at_minimum_5pct,
                "at_minimum_run_id": (day.at_minimum_run_id if day.at_minimum_run_id is not None else ""),
                "at_minimum_run_length_days": day.at_minimum_run_length_days,
                "is_floor_binding_regime_7d": day.is_floor_binding_regime_7d,
            }
        )
    _validate_output_rows(out)
    return out


def summarize_linkage(daily: list[DailyAggregate], *, min_blob_fee_wei: int, threshold_wei: int) -> dict[str, float | int]:
    post_days = [d for d in daily if d.is_post_dencun]
    post_with_finite_str = [d for d in post_days if math.isfinite(d.ecosystem_str)]
    at_min_days = [d for d in post_days if d.is_at_minimum_5pct == 1]
    non_at_min_days = [d for d in post_days if d.is_at_minimum_5pct == 0]
    floor_binding_days = [d for d in post_days if d.is_floor_binding_regime_7d == 1]

    at_min_str = [d.ecosystem_str for d in at_min_days if math.isfinite(d.ecosystem_str)]
    non_at_min_str = [d.ecosystem_str for d in non_at_min_days if math.isfinite(d.ecosystem_str)]

    corr_x: list[float] = []
    corr_y: list[float] = []
    for d in post_days:
        if not math.isfinite(d.ecosystem_str):
            continue
        corr_x.append(float(d.is_at_minimum_5pct))
        corr_y.append(d.ecosystem_str)

    post_count = len(post_days)
    at_min_count = len(at_min_days)
    floor_count = len(floor_binding_days)

    summary: dict[str, float | int] = {
        "n_days_total": len(daily),
        "n_days_post_dencun": post_count,
        "min_blob_fee_post_wei": min_blob_fee_wei,
        "at_minimum_threshold_wei": threshold_wei,
        "n_days_at_minimum_5pct_post": at_min_count,
        "n_days_floor_binding_7d_post": floor_count,
        "at_minimum_fraction_post": (float(at_min_count) / float(post_count)) if post_count > 0 else math.nan,
        "floor_binding_fraction_post": (float(floor_count) / float(post_count)) if post_count > 0 else math.nan,
        "mean_str_post": _mean([d.ecosystem_str for d in post_with_finite_str]),
        "mean_str_at_minimum_post": _mean(at_min_str),
        "mean_str_not_at_minimum_post": _mean(non_at_min_str),
        "mean_str_diff_at_min_minus_not_post": (_mean(at_min_str) - _mean(non_at_min_str)),
        "corr_str_vs_at_minimum_post": _pearson_corr(corr_x, corr_y),
    }
    return summary


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(OUTPUT_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in OUTPUT_COLUMNS})


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


def _format_metric(value: float | int, *, decimals: int = 4) -> str:
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        return "nan"
    return f"{value:.{decimals}f}"


def _format_pct(value: float) -> str:
    if not math.isfinite(value):
        return "nan"
    return f"{100.0 * value:.1f}%"


def _svg_linkage_chart(
    *,
    daily: list[DailyAggregate],
    summary: dict[str, float | int],
    threshold_wei: int,
    min_blob_fee_wei: int,
) -> str:
    if not daily:
        raise ValueError("empty daily series")

    width = 1120
    height = 620
    margin_left = 78
    margin_right = 22
    margin_top = 70
    margin_bottom = 52
    panel_gap = 64
    panel_height = 190
    plot_width = width - margin_left - margin_right
    panel1_top = margin_top
    panel2_top = panel1_top + panel_height + panel_gap
    panel2_bottom = panel2_top + panel_height

    xs = list(range(len(daily)))
    str_vals = [d.ecosystem_str for d in daily]
    blob_vals_gwei = [((float(d.l1_blob_base_fee_wei) / float(WEI_PER_GWEI)) if d.l1_blob_base_fee_wei is not None else math.nan) for d in daily]
    threshold_gwei = float(threshold_wei) / float(WEI_PER_GWEI)

    x_min = min(xs)
    x_max = max(xs)
    if x_min == x_max:
        x_min -= 1
        x_max += 1

    def x_px(x: int) -> float:
        return margin_left + plot_width * ((x - x_min) / float(x_max - x_min))

    def y_scale(values: list[float], include: list[float] | None = None) -> tuple[float, float]:
        finite_vals = [v for v in values if math.isfinite(v)]
        if include is not None:
            finite_vals.extend(v for v in include if math.isfinite(v))
        if not finite_vals:
            return (0.0, 1.0)
        y_min = min(finite_vals)
        y_max = max(finite_vals)
        if y_min == y_max:
            y_min -= 0.01
            y_max += 0.01
        pad = 0.06 * (y_max - y_min)
        return (y_min - pad, y_max + pad)

    str_y0, str_y1 = y_scale(str_vals)
    blob_y0, blob_y1 = y_scale(blob_vals_gwei, include=[threshold_gwei])

    def y1_px(y: float) -> float:
        return panel1_top + panel_height * (1.0 - ((y - str_y0) / float(str_y1 - str_y0)))

    def y2_px(y: float) -> float:
        return panel2_top + panel_height * (1.0 - ((y - blob_y0) / float(blob_y1 - blob_y0)))

    at_min_shades: list[str] = []
    floor_shades: list[str] = []
    for idx, d in enumerate(daily):
        if d.is_at_minimum_5pct == 1:
            xp = x_px(idx)
            at_min_shades.append(
                f'<rect x="{xp-1.6:.2f}" y="{panel1_top}" width="3.2" height="{(panel2_bottom - panel1_top)}" fill="#10b981" opacity="0.12" />'
            )
        if d.is_floor_binding_regime_7d == 1:
            xp = x_px(idx)
            floor_shades.append(
                f'<rect x="{xp-1.6:.2f}" y="{panel1_top}" width="3.2" height="{(panel2_bottom - panel1_top)}" fill="#047857" opacity="0.28" />'
            )

    dencun_idx = next((i for i, d in enumerate(daily) if d.date_obj >= DENCUN_DATE_UTC), None)
    dencun_line = ""
    if dencun_idx is not None:
        xline = x_px(dencun_idx)
        dencun_line = (
            f'<line x1="{xline:.2f}" y1="{panel1_top}" x2="{xline:.2f}" y2="{panel2_bottom}" '
            'stroke="#d97706" stroke-width="2" stroke-dasharray="6 6" />'
        )

    def y_ticks(y0: float, y1: float, y_fn: Any, decimals: int) -> list[str]:
        ticks = 5
        out: list[str] = []
        for i in range(ticks + 1):
            value = y0 + (y1 - y0) * (i / float(ticks))
            yp = y_fn(value)
            out.append(f'<line x1="{margin_left-6}" y1="{yp:.2f}" x2="{margin_left}" y2="{yp:.2f}" stroke="#333" />')
            out.append(
                f'<text x="{margin_left-10}" y="{yp+4:.2f}" font-size="11" text-anchor="end" fill="#111">{value:.{decimals}f}</text>'
            )
        return out

    def polyline_segments(color: str, segments: list[list[tuple[int, float]]], y_fn: Any, *, width_px: float = 2.4) -> list[str]:
        elems: list[str] = []
        for segment in segments:
            if len(segment) < 2:
                continue
            points = " ".join(f"{x_px(x):.2f},{y_fn(y):.2f}" for x, y in segment)
            elems.append(f'<polyline fill="none" stroke="{color}" stroke-width="{width_px}" points="{points}" />')
        return elems

    str_segments = _segment_points(xs, str_vals)
    blob_segments = _segment_points(xs, blob_vals_gwei)

    post_indices = [i for i, d in enumerate(daily) if d.is_post_dencun]
    threshold_line = ""
    threshold_label = ""
    if post_indices:
        x_start = x_px(post_indices[0])
        x_end = x_px(post_indices[-1])
        y_thr = y2_px(threshold_gwei)
        threshold_line = (
            f'<line x1="{x_start:.2f}" y1="{y_thr:.2f}" x2="{x_end:.2f}" y2="{y_thr:.2f}" '
            'stroke="#f97316" stroke-width="2" stroke-dasharray="7 5" />'
        )
        threshold_label = (
            f'<text x="{x_end-6:.2f}" y="{y_thr-6:.2f}" font-size="11" text-anchor="end" fill="#9a3412">at-min threshold</text>'
        )

    x_tick_positions = sorted(set([0, len(daily) // 2, len(daily) - 1] + ([dencun_idx] if dencun_idx is not None else [])))
    x_ticks: list[str] = []
    for i in x_tick_positions:
        if i < 0 or i >= len(daily):
            continue
        xp = x_px(i)
        label = daily[i].date_utc
        x_ticks.append(f'<line x1="{xp:.2f}" y1="{panel2_bottom}" x2="{xp:.2f}" y2="{panel2_bottom+5}" stroke="#333" />')
        x_ticks.append(f'<text x="{xp:.2f}" y="{panel2_bottom+18}" font-size="11" text-anchor="middle" fill="#111">{label}</text>')

    at_fraction = float(summary["at_minimum_fraction_post"])
    floor_fraction = float(summary["floor_binding_fraction_post"])
    summary_lines = [
        f"Post days: {summary['n_days_post_dencun']}",
        f"At-min days: {summary['n_days_at_minimum_5pct_post']} ({_format_pct(at_fraction)})",
        f"Floor-binding >=7d days: {summary['n_days_floor_binding_7d_post']} ({_format_pct(floor_fraction)})",
        f"Min post blob fee (wei): {summary['min_blob_fee_post_wei']}",
        f"At-min threshold (wei): {summary['at_minimum_threshold_wei']}",
        f"Mean STR at-min: {_format_metric(float(summary['mean_str_at_minimum_post']), decimals=4)}",
        f"Mean STR not at-min: {_format_metric(float(summary['mean_str_not_at_minimum_post']), decimals=4)}",
        f"Corr(STR, at-min): {_format_metric(float(summary['corr_str_vs_at_minimum_post']), decimals=4)}",
    ]
    summary_text = [
        '<rect x="718" y="8" width="390" height="140" fill="#f8fafc" stroke="#cbd5e1" />',
        '<text x="730" y="28" font-size="12" fill="#111">Sample linkage summary</text>',
    ]
    for i, line in enumerate(summary_lines):
        summary_text.append(f'<text x="730" y="{46 + 14 * i}" font-size="11" fill="#111">{line}</text>')

    legend = "\n".join(
        [
            '<rect x="78" y="12" width="10" height="10" fill="#2563eb" />',
            '<text x="93" y="21" font-size="12" fill="#111">ecosystem STR</text>',
            '<rect x="210" y="12" width="10" height="10" fill="#dc2626" />',
            '<text x="225" y="21" font-size="12" fill="#111">blob base fee (gwei)</text>',
            '<rect x="390" y="12" width="10" height="10" fill="#10b981" opacity="0.22" />',
            '<text x="405" y="21" font-size="12" fill="#111">at-minimum day</text>',
            '<rect x="530" y="12" width="10" height="10" fill="#047857" opacity="0.35" />',
            '<text x="545" y="21" font-size="12" fill="#111">floor-binding regime day (>=7)</text>',
            '<line x1="78" y1="35" x2="104" y2="35" stroke="#d97706" stroke-width="2" stroke-dasharray="6 6" />',
            '<text x="110" y="39" font-size="12" fill="#111">Dencun boundary (2024-03-13)</text>',
            '<line x1="315" y1="35" x2="341" y2="35" stroke="#f97316" stroke-width="2" stroke-dasharray="7 5" />',
            '<text x="347" y="39" font-size="12" fill="#111">at-min threshold</text>',
        ]
    )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect x="0" y="0" width="100%" height="100%" fill="white" />',
            '<text x="78" y="56" font-size="13" fill="#111">Top: ecosystem STR (daily)</text>',
            '<text x="78" y="310" font-size="13" fill="#111">Bottom: Ethereum L1 blob base fee (daily, gwei)</text>',
            legend,
            *summary_text,
            f'<line x1="{margin_left}" y1="{panel1_top}" x2="{margin_left}" y2="{panel1_top + panel_height}" stroke="#111" />',
            f'<line x1="{margin_left}" y1="{panel1_top + panel_height}" x2="{margin_left + plot_width}" y2="{panel1_top + panel_height}" stroke="#111" />',
            f'<line x1="{margin_left}" y1="{panel2_top}" x2="{margin_left}" y2="{panel2_top + panel_height}" stroke="#111" />',
            f'<line x1="{margin_left}" y1="{panel2_top + panel_height}" x2="{margin_left + plot_width}" y2="{panel2_top + panel_height}" stroke="#111" />',
            *y_ticks(str_y0, str_y1, y1_px, 3),
            *y_ticks(blob_y0, blob_y1, y2_px, 2),
            *at_min_shades,
            *floor_shades,
            dencun_line,
            threshold_line,
            threshold_label,
            *polyline_segments("#2563eb", str_segments, y1_px),
            *polyline_segments("#dc2626", blob_segments, y2_px),
            *x_ticks,
            "</svg>",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="blob_floor_binding_str_link.py")
    p.add_argument("--sample", action="store_true", help="Use the committed sample v2 panel (default behavior when --panel is omitted)")
    p.add_argument("--panel", default=None, help="Path to a daily_rollup_panel v2 CSV")
    p.add_argument("--tag", default=None, help="Output tag suffix (default: sample/full)")
    return p


def main(argv: list[str]) -> None:
    root = _repo_root()
    args = build_parser().parse_args(argv[1:])

    if args.sample and args.panel is not None:
        raise SystemExit("Use either --sample or --panel, not both")

    if args.panel is None:
        panel_abs = root / "data/samples/panels/daily_rollup_panel_v2_sample.csv"
        tag = args.tag or "sample"
    else:
        panel_path = Path(args.panel)
        panel_abs = panel_path if panel_path.is_absolute() else (root / panel_path)
        tag = args.tag or "full"

    if not panel_abs.exists():
        raise SystemExit(f"panel not found: {panel_abs}")

    panel_rel = str(_ensure_within_repo(root, panel_abs.resolve()))
    panel_sha = _sha256_file(panel_abs)

    fieldnames, rows = load_panel_csv(panel_abs)
    _validate_input_columns(fieldnames)

    daily = compute_daily_series(rows)
    min_blob_fee_wei, threshold_wei = apply_at_minimum_and_floor_binding(daily)
    summary = summarize_linkage(daily, min_blob_fee_wei=min_blob_fee_wei, threshold_wei=threshold_wei)
    output_rows = build_output_rows(daily, threshold_wei)

    tables_dir = root / "reports/tables"
    figs_dir = root / "reports/figures"
    out_csv = tables_dir / f"blob_floor_binding_str_link_{tag}.csv"
    out_svg = figs_dir / f"blob_floor_binding_str_link_{tag}.svg"
    out_run = tables_dir / f"blob_floor_binding_str_link_{tag}_run.json"

    _write_csv(out_csv, output_rows)

    svg = _svg_linkage_chart(
        daily=daily,
        summary=summary,
        threshold_wei=threshold_wei,
        min_blob_fee_wei=min_blob_fee_wei,
    )
    _write_text(out_svg, svg)

    now = datetime.now(timezone.utc).isoformat()
    run_manifest: dict[str, object] = {
        "created_at_utc": now,
        "script_path": str(_ensure_within_repo(root, Path(__file__).resolve())),
        "git_sha": _git_sha(root),
        "command": " ".join(json.dumps(t) for t in sys.argv),
        "parameters": {
            "dencun_date_utc": DENCUN_DATE_UTC.isoformat(),
            "at_minimum_multiplier_numerator": AT_MIN_MULTIPLIER_NUM,
            "at_minimum_multiplier_denominator": AT_MIN_MULTIPLIER_DEN,
            "floor_binding_min_run_days": FLOOR_BINDING_MIN_RUN_DAYS,
            "at_minimum_threshold_wei": threshold_wei,
            "min_blob_fee_post_wei": min_blob_fee_wei,
        },
        "summary": summary,
        "inputs": [
            {
                "path": panel_rel,
                "sha256": panel_sha,
                "bytes": panel_abs.stat().st_size,
            }
        ],
        "outputs": [
            {
                "path": str(_ensure_within_repo(root, out_csv)),
                "sha256": _sha256_file(out_csv),
                "bytes": out_csv.stat().st_size,
            },
            {
                "path": str(_ensure_within_repo(root, out_svg)),
                "sha256": _sha256_file(out_svg),
                "bytes": out_svg.stat().st_size,
            },
        ],
    }
    out_run.parent.mkdir(parents=True, exist_ok=True)
    out_run.write_text(json.dumps(run_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "tag": tag,
                "summary": summary,
                "outputs": [str(out_csv), str(out_svg), str(out_run)],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main(sys.argv)
