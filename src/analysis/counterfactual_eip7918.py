from __future__ import annotations

"""EIP-7918 reserve/floor counterfactual (applied floor) + figure (deterministic).

Implements the W0-locked counterfactual assumption A001:
- Do NOT simulate a new equilibrium.
- Apply the EIP-7918 reserve price as a deterministic floor to the observed blob base fee.

Inputs (sample mode):
- `data/samples/panels/daily_rollup_panel_v2_sample.csv`

Inputs (full mode):
- `--panel <path>` pointing to a contract-v2 daily rollup panel CSV
  (see `contracts/schemas/panel_schema_str_v2.yaml`)
- `--panel-manifest <path>` (required in full mode): processed manifest JSON for the input panel

Outputs (stable names):
- `reports/tables/eip7918_counterfactual_summary_<tag>.csv`
  - Includes a machine-readable metadata JSON block in the header area.
- `reports/figures/eip7918_counterfactual_<tag>.svg`
- `reports/tables/eip7918_counterfactual_summary_<tag>_run.json`
  - Traceability: assumptions + inputs/outputs + hashes.

How to run:
- Sample:
  `python src/analysis/counterfactual_eip7918.py --sample`
- Full (example):
  `python src/analysis/counterfactual_eip7918.py --panel data/processed/panels/daily_rollup_panel_v2.csv --panel-manifest data/processed_manifest/daily_rollup_panel_v2_YYYY-MM-DD.json --tag full`
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


# Locked protocol constants (docs/protocol.md; T098).
DENCUN_DATE_UTC = date(2024, 3, 13)
BLOB_BASE_COST = 8192
GAS_PER_BLOB = 131072
WEI_PER_ETH = 10**18


SUMMARY_COLUMNS = [
    "date_utc",
    "l2_fees_eth_sum",
    "rent_paid_eth_sum",
    "rent_paid_cf_eth_sum",
    "delta_rent_blob_burn_eth_sum",
    "str_observed",
    "str_counterfactual",
    "str_delta",
    "included_rollup_days",
    "l1_base_fee_per_gas_wei",
    "l1_blob_base_fee_wei",
    "reserve_blob_base_fee_wei",
    "cf_blob_base_fee_wei",
    "floor_binding",
]


Row = dict[str, str]


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
    v = row.get(key)
    if not isinstance(v, str) or v.strip() == "":
        raise SystemExit(f"Missing required field {key!r}")
    return v.strip()


def _parse_date_utc(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid date_utc (expected YYYY-MM-DD): {value!r}") from exc


def _parse_float_required(row: Row, key: str) -> float:
    s = _require_str(row, key)
    try:
        v = float(s)
    except ValueError as exc:
        raise SystemExit(f"Invalid float for {key!r}: {s!r}") from exc
    if not math.isfinite(v):
        raise SystemExit(f"Non-finite value for {key!r}: {s!r}")
    return v


def _parse_int_required(row: Row, key: str) -> int:
    s = _require_str(row, key)
    try:
        return int(s)
    except ValueError as exc:
        raise SystemExit(f"Invalid int for {key!r}: {s!r}") from exc


def _parse_int_optional(row: Row, key: str) -> int | None:
    v = row.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        raise SystemExit(f"Invalid type for {key!r}: expected string, got {type(v)}")
    s = v.strip()
    if s == "":
        return None
    try:
        return int(s)
    except ValueError as exc:
        raise SystemExit(f"Invalid int for {key!r}: {s!r}") from exc


def reserve_blob_base_fee_wei(base_fee_per_gas_wei: int) -> int:
    if base_fee_per_gas_wei < 0:
        raise ValueError("base_fee_per_gas_wei must be >= 0")
    return (BLOB_BASE_COST * base_fee_per_gas_wei) // GAS_PER_BLOB


def blob_base_fee_cf_wei(*, observed_blob_base_fee_wei: int, base_fee_per_gas_wei: int) -> int:
    reserve = reserve_blob_base_fee_wei(base_fee_per_gas_wei)
    return max(int(observed_blob_base_fee_wei), int(reserve))


def load_panel_csv(path: Path) -> tuple[list[str], list[Row]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        raw_lines = f.readlines()
    lines = [ln for ln in raw_lines if not ln.lstrip().startswith("#") and ln.strip() != ""]
    if not lines:
        raise SystemExit(f"Empty CSV (after stripping comments): {path}")

    reader = csv.DictReader(lines)
    if reader.fieldnames is None:
        raise SystemExit(f"Missing CSV header: {path}")
    fieldnames = list(reader.fieldnames)
    rows: list[Row] = [dict(r) for r in reader]
    return fieldnames, rows


def _validate_required_columns(fieldnames: list[str]) -> None:
    required = {"date_utc", "rollup_id", "l2_fees_eth", "rent_paid_eth", "l1_base_fee_per_gas_wei"}
    missing = sorted(c for c in required if c not in set(fieldnames))
    if missing:
        raise SystemExit(f"Input panel is missing required columns: {missing}")


@dataclass
class DailyAccumulator:
    l2_fees_eth_sum: float = 0.0
    rent_paid_eth_sum: float = 0.0
    rent_paid_cf_eth_sum: float = 0.0
    delta_rent_blob_burn_eth_sum: float = 0.0
    included_rollup_days: int = 0

    # Global (duplicated on each rollup-day row).
    l1_base_fee_per_gas_wei: int | None = None
    l1_blob_base_fee_wei: int | None = None
    reserve_blob_base_fee_wei: int | None = None
    cf_blob_base_fee_wei: int | None = None
    floor_binding: bool | None = None


def compute_daily_counterfactual(rows: Iterable[Row]) -> list[dict[str, object]]:
    per_day: dict[str, DailyAccumulator] = {}

    for row in rows:
        date_str = _require_str(row, "date_utc")
        rollup_id = _require_str(row, "rollup_id")
        d = _parse_date_utc(date_str)

        fees = _parse_float_required(row, "l2_fees_eth")
        rent = _parse_float_required(row, "rent_paid_eth")
        if fees < 0 or rent < 0:
            raise SystemExit(f"Negative values not allowed: {date_str=} {rollup_id=} {fees=} {rent=}")

        base_fee_gas_wei = _parse_int_required(row, "l1_base_fee_per_gas_wei")
        if base_fee_gas_wei < 0:
            raise SystemExit(f"Negative l1_base_fee_per_gas_wei not allowed: {date_str=} {base_fee_gas_wei=}")

        blob_fee_wei = _parse_int_optional(row, "l1_blob_base_fee_wei")
        blob_gas_used = _parse_int_optional(row, "rollup_blob_gas_used")
        if blob_fee_wei is not None and blob_fee_wei < 0:
            raise SystemExit(f"Negative l1_blob_base_fee_wei not allowed: {date_str=} {blob_fee_wei=}")
        if blob_gas_used is not None and blob_gas_used < 0:
            raise SystemExit(f"Negative rollup_blob_gas_used not allowed: {date_str=} {rollup_id=} {blob_gas_used=}")

        is_post = d >= DENCUN_DATE_UTC
        if is_post:
            if blob_fee_wei is None:
                raise SystemExit(f"Missing required post-Dencun field l1_blob_base_fee_wei: {date_str=} {rollup_id=}")
            if blob_gas_used is None:
                raise SystemExit(f"Missing required post-Dencun field rollup_blob_gas_used: {date_str=} {rollup_id=}")

        reserve_wei: int | None = None
        cf_blob_fee_wei: int | None = None
        floor_binding: bool | None = None
        delta_blob_burn_wei = 0

        if is_post:
            assert blob_fee_wei is not None
            assert blob_gas_used is not None
            reserve_wei = reserve_blob_base_fee_wei(base_fee_gas_wei)
            cf_blob_fee_wei = max(blob_fee_wei, reserve_wei)
            floor_binding = bool(reserve_wei > blob_fee_wei)
            delta_blob_burn_wei = int(blob_gas_used) * int(cf_blob_fee_wei - blob_fee_wei)

        delta_eth = float(delta_blob_burn_wei) / float(WEI_PER_ETH)
        rent_cf = rent + delta_eth

        acc = per_day.get(date_str)
        if acc is None:
            acc = DailyAccumulator()
            per_day[date_str] = acc

        # Enforce global duplicated fields are consistent across rollups for the same date.
        if acc.l1_base_fee_per_gas_wei is None:
            acc.l1_base_fee_per_gas_wei = base_fee_gas_wei
        elif acc.l1_base_fee_per_gas_wei != base_fee_gas_wei:
            raise SystemExit(f"Inconsistent l1_base_fee_per_gas_wei within date: {date_str=}")

        if is_post:
            assert blob_fee_wei is not None
            assert reserve_wei is not None
            assert cf_blob_fee_wei is not None
            assert floor_binding is not None

            if acc.l1_blob_base_fee_wei is None:
                acc.l1_blob_base_fee_wei = blob_fee_wei
            elif acc.l1_blob_base_fee_wei != blob_fee_wei:
                raise SystemExit(f"Inconsistent l1_blob_base_fee_wei within date: {date_str=}")

            if acc.reserve_blob_base_fee_wei is None:
                acc.reserve_blob_base_fee_wei = reserve_wei
            elif acc.reserve_blob_base_fee_wei != reserve_wei:
                raise SystemExit(f"Inconsistent reserve_blob_base_fee_wei within date: {date_str=}")

            if acc.cf_blob_base_fee_wei is None:
                acc.cf_blob_base_fee_wei = cf_blob_fee_wei
            elif acc.cf_blob_base_fee_wei != cf_blob_fee_wei:
                raise SystemExit(f"Inconsistent cf_blob_base_fee_wei within date: {date_str=}")

            if acc.floor_binding is None:
                acc.floor_binding = floor_binding
            elif acc.floor_binding != floor_binding:
                raise SystemExit(f"Inconsistent floor_binding within date: {date_str=}")

        acc.l2_fees_eth_sum += float(fees)
        acc.rent_paid_eth_sum += float(rent)
        acc.rent_paid_cf_eth_sum += float(rent_cf)
        acc.delta_rent_blob_burn_eth_sum += float(delta_eth)
        acc.included_rollup_days += 1

    out: list[dict[str, object]] = []
    for date_str in sorted(per_day.keys()):
        acc = per_day[date_str]
        fees_sum = acc.l2_fees_eth_sum
        rent_sum = acc.rent_paid_eth_sum
        rent_cf_sum = acc.rent_paid_cf_eth_sum

        str_obs = math.nan if fees_sum == 0 else (rent_sum / fees_sum)
        str_cf = math.nan if fees_sum == 0 else (rent_cf_sum / fees_sum)
        str_delta = str_cf - str_obs if (math.isfinite(str_cf) and math.isfinite(str_obs)) else math.nan

        out.append(
            {
                "date_utc": date_str,
                "l2_fees_eth_sum": f"{fees_sum:.8f}",
                "rent_paid_eth_sum": f"{rent_sum:.8f}",
                "rent_paid_cf_eth_sum": f"{rent_cf_sum:.8f}",
                "delta_rent_blob_burn_eth_sum": f"{acc.delta_rent_blob_burn_eth_sum:.8f}",
                "str_observed": f"{str_obs:.10f}",
                "str_counterfactual": f"{str_cf:.10f}",
                "str_delta": f"{str_delta:.10f}",
                "included_rollup_days": acc.included_rollup_days,
                "l1_base_fee_per_gas_wei": acc.l1_base_fee_per_gas_wei if acc.l1_base_fee_per_gas_wei is not None else "",
                "l1_blob_base_fee_wei": acc.l1_blob_base_fee_wei if acc.l1_blob_base_fee_wei is not None else "",
                "reserve_blob_base_fee_wei": acc.reserve_blob_base_fee_wei if acc.reserve_blob_base_fee_wei is not None else "",
                "cf_blob_base_fee_wei": acc.cf_blob_base_fee_wei if acc.cf_blob_base_fee_wei is not None else "",
                "floor_binding": (("true" if acc.floor_binding else "false") if acc.floor_binding is not None else ""),
            }
        )

    return out


def _write_summary_csv(path: Path, *, meta: dict[str, object], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta_json = json.dumps(meta, sort_keys=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(f"# meta_json: {meta_json}\n")
        f.write("\n")
        w = csv.DictWriter(f, fieldnames=list(SUMMARY_COLUMNS), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in SUMMARY_COLUMNS})


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


def _svg_two_line_chart(
    *,
    width: int,
    height: int,
    xs: list[int],
    ys_a: list[float],
    ys_b: list[float],
    dencun_x: int | None,
    binding_xs: list[int],
    title: str,
    label_a: str,
    label_b: str,
) -> str:
    if len(xs) != len(ys_a) or len(xs) != len(ys_b):
        raise ValueError("series length mismatch")
    if not xs:
        raise ValueError("empty chart series")

    margin_left = 60
    margin_right = 20
    margin_top = 30
    margin_bottom = 40
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    finite_vals: list[float] = [v for v in ys_a + ys_b if math.isfinite(v)]
    if not finite_vals:
        raise ValueError("no finite points to plot")
    y_min = min(finite_vals)
    y_max = max(finite_vals)
    if y_min == y_max:
        y_min -= 0.01
        y_max += 0.01
    pad = 0.05 * (y_max - y_min)
    y0 = y_min - pad
    y1 = y_max + pad

    x_min = min(xs)
    x_max = max(xs)
    if x_min == x_max:
        x_min -= 1
        x_max += 1

    def x_px(x: int) -> float:
        return margin_left + plot_w * ((x - x_min) / float(x_max - x_min))

    def y_px(y: float) -> float:
        return margin_top + plot_h * (1.0 - ((y - y0) / float(y1 - y0)))

    # Binding day shading (very light).
    shade_elems: list[str] = []
    for x in binding_xs:
        if x < x_min or x > x_max:
            continue
        xp = x_px(x)
        shade_elems.append(
            f'<rect x="{xp-1.0:.2f}" y="{margin_top}" width="2.0" height="{plot_h}" fill="#10b981" opacity="0.15" />'
        )

    dencun_line = ""
    if dencun_x is not None and x_min <= dencun_x <= x_max:
        xline = x_px(dencun_x)
        dencun_line = (
            f'<line x1="{xline:.2f}" y1="{margin_top}" x2="{xline:.2f}" y2="{margin_top + plot_h}" '
            'stroke="#d97706" stroke-width="2" stroke-dasharray="6 6" />'
        )

    # Simple y ticks.
    yticks = 5
    tick_elems: list[str] = []
    for i in range(yticks + 1):
        yv = y0 + (y1 - y0) * (i / float(yticks))
        yp = y_px(yv)
        tick_elems.append(f'<line x1="{margin_left-5}" y1="{yp:.2f}" x2="{margin_left}" y2="{yp:.2f}" stroke="#333" />')
        tick_elems.append(
            f'<text x="{margin_left-8}" y="{yp+4:.2f}" font-size="11" text-anchor="end" fill="#111">{yv:.3f}</text>'
        )

    def polyline_segments(color: str, segments: list[list[tuple[int, float]]]) -> list[str]:
        elems: list[str] = []
        for seg in segments:
            if len(seg) < 2:
                continue
            points = " ".join(f"{x_px(x):.2f},{y_px(y):.2f}" for x, y in seg)
            elems.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{points}" />')
        return elems

    seg_a = _segment_points(xs, ys_a)
    seg_b = _segment_points(xs, ys_b)

    legend = "\n".join(
        [
            f'<rect x="{margin_left+10}" y="{margin_top+5}" width="10" height="10" fill="#2563eb" />',
            f'<text x="{margin_left+25}" y="{margin_top+14}" font-size="12" fill="#111">{label_a}</text>',
            f'<rect x="{margin_left+130}" y="{margin_top+5}" width="10" height="10" fill="#dc2626" />',
            f'<text x="{margin_left+145}" y="{margin_top+14}" font-size="12" fill="#111">{label_b}</text>',
            f'<rect x="{margin_left+260}" y="{margin_top+5}" width="10" height="10" fill="#10b981" opacity="0.35" />',
            f'<text x="{margin_left+275}" y="{margin_top+14}" font-size="12" fill="#111">floor binding</text>',
        ]
    )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect x="0" y="0" width="100%" height="100%" fill="white" />',
            f'<text x="{margin_left}" y="20" font-size="14" fill="#111">{title}</text>',
            f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#111" />',
            f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" stroke="#111" />',
            *tick_elems,
            legend,
            *shade_elems,
            dencun_line,
            *polyline_segments("#2563eb", seg_a),
            *polyline_segments("#dc2626", seg_b),
            "</svg>",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="counterfactual_eip7918.py")
    p.add_argument("--sample", action="store_true", help="Use the committed sample v2 panel")
    p.add_argument("--panel", default=None, help="Path to a daily_rollup_panel v2 CSV")
    p.add_argument("--panel-manifest", default=None, help="Processed-manifest JSON for the input panel (required for --panel)")
    p.add_argument("--tag", default=None, help="Output tag suffix (default: sample/full)")
    return p


def main(argv: list[str]) -> None:
    root = _repo_root()
    args = build_parser().parse_args(argv[1:])

    if args.sample:
        panel_abs = root / "data/samples/panels/daily_rollup_panel_v2_sample.csv"
        tag = args.tag or "sample"
    else:
        if args.panel is None:
            raise SystemExit("Missing --panel (or use --sample)")
        if args.panel_manifest is None:
            raise SystemExit("Missing --panel-manifest (required for full mode provenance)")
        panel_path = Path(args.panel)
        panel_abs = panel_path if panel_path.is_absolute() else (root / panel_path)
        tag = args.tag or "full"

    if not panel_abs.exists():
        raise SystemExit(f"panel not found: {panel_abs}")

    panel_rel = str(_ensure_within_repo(root, panel_abs.resolve()))
    panel_sha = _sha256_file(panel_abs)

    manifest_rel = None
    manifest_sha = None
    manifest_bytes = None
    if args.panel_manifest is not None:
        manifest_path = Path(args.panel_manifest)
        manifest_abs = manifest_path if manifest_path.is_absolute() else (root / manifest_path)
        if not manifest_abs.exists():
            raise SystemExit(f"panel manifest not found: {manifest_abs}")
        manifest_rel = str(_ensure_within_repo(root, manifest_abs.resolve()))
        manifest_sha = _sha256_file(manifest_abs)
        manifest_bytes = manifest_abs.stat().st_size

    fieldnames, rows = load_panel_csv(panel_abs)
    _validate_required_columns(fieldnames)
    summary_rows = compute_daily_counterfactual(rows)

    binding_xs: list[int] = []
    xs: list[int] = list(range(len(summary_rows)))
    ys_obs: list[float] = []
    ys_cf: list[float] = []
    dates: list[date] = []
    for i, r in enumerate(summary_rows):
        dates.append(_parse_date_utc(str(r["date_utc"])))
        ys_obs.append(float(r["str_observed"]))
        ys_cf.append(float(r["str_counterfactual"]))
        if str(r.get("floor_binding") or "").strip().lower() == "true":
            binding_xs.append(i)

    dencun_idx = next((i for i, d in enumerate(dates) if d >= DENCUN_DATE_UTC), None)

    tables_dir = root / "reports/tables"
    figs_dir = root / "reports/figures"
    out_csv = tables_dir / f"eip7918_counterfactual_summary_{tag}.csv"
    out_svg = figs_dir / f"eip7918_counterfactual_{tag}.svg"
    out_run = tables_dir / f"eip7918_counterfactual_summary_{tag}_run.json"

    now = datetime.now(timezone.utc).isoformat()
    assumptions = {
        "assumption_ids": ["A001"],
        "description": "Applied-floor counterfactual (no equilibrium simulation).",
        "constants": {"BLOB_BASE_COST": BLOB_BASE_COST, "GAS_PER_BLOB": GAS_PER_BLOB, "WEI_PER_ETH": WEI_PER_ETH},
        "dencun_date_utc": DENCUN_DATE_UTC.isoformat(),
        "formulas": {
            "reserve_blob_base_fee_wei": "floor(BLOB_BASE_COST * base_fee_per_gas_wei / GAS_PER_BLOB)",
            "base_fee_per_blob_gas_cf_wei": "max(base_fee_per_blob_gas_wei, reserve_blob_base_fee_wei)",
        },
    }

    meta = {
        "schema_version": 1,
        "created_at_utc": now,
        "script_path": str(_ensure_within_repo(root, Path(__file__).resolve())),
        "git_sha": _git_sha(root),
        "tag": tag,
        "assumptions": assumptions,
        "inputs": {
            "panel_path": panel_rel,
            "panel_sha256": panel_sha,
            "panel_bytes": panel_abs.stat().st_size,
            "panel_manifest_path": manifest_rel,
            "panel_manifest_sha256": manifest_sha,
        },
    }

    _write_summary_csv(out_csv, meta=meta, rows=summary_rows)

    svg = _svg_two_line_chart(
        width=900,
        height=420,
        xs=xs,
        ys_a=ys_obs,
        ys_b=ys_cf,
        dencun_x=dencun_idx,
        binding_xs=binding_xs,
        title=f"Ecosystem STR: observed vs EIP-7918 floor counterfactual — {tag}",
        label_a="observed",
        label_b="counterfactual",
    )
    _write_text(out_svg, svg)

    run_manifest: dict[str, Any] = {
        "created_at_utc": now,
        "script_path": str(_ensure_within_repo(root, Path(__file__).resolve())),
        "git_sha": _git_sha(root),
        "command": " ".join(json.dumps(t) for t in sys.argv),
        "assumptions": assumptions,
        "inputs": [
            {"path": panel_rel, "sha256": panel_sha, "bytes": panel_abs.stat().st_size},
        ],
        "outputs": [],
    }
    if manifest_rel is not None and manifest_sha is not None and manifest_bytes is not None:
        run_manifest["inputs"].append({"path": manifest_rel, "sha256": manifest_sha, "bytes": manifest_bytes})

    run_manifest["outputs"] = [
        {"path": str(_ensure_within_repo(root, out_csv)), "sha256": _sha256_file(out_csv), "bytes": out_csv.stat().st_size},
        {"path": str(_ensure_within_repo(root, out_svg)), "sha256": _sha256_file(out_svg), "bytes": out_svg.stat().st_size},
    ]
    out_run.parent.mkdir(parents=True, exist_ok=True)
    out_run.write_text(json.dumps(run_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {"ok": True, "tag": tag, "outputs": [str(out_csv), str(out_svg), str(out_run)]},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main(sys.argv)
