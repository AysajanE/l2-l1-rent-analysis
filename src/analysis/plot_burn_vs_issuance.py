from __future__ import annotations

"""Burn vs issuance daily time series + deterministic SVG (sample mode default).

This is an analysis-side artifact builder: it must not make any network calls.

Inputs (sample mode; default):
- `data/samples/panels/daily_rollup_panel_v2_sample.csv`
- `data/samples/issuance/issuance_daily_sample.csv`

Inputs (full mode):
- `--panel <path>` pointing to a contract-v2 daily rollup panel CSV
  (see `contracts/schemas/panel_schema_str_v2.yaml` for field names)
- `--issuance <path>` optional daily issuance CSV, required unless the panel provides
  non-empty `issuance_eth` values (gross consensus-layer issuance; not net of burn).

Outputs (stable names):
- `reports/tables/burn_vs_issuance_<tag>.csv`
- `reports/figures/burn_vs_issuance_<tag>.svg`
- `reports/tables/burn_vs_issuance_<tag>_run.json`
  - Traceability: timestamp, command, git SHA (if available), and input/output hashes.

How to run:
- Sample (default):
  `python src/analysis/plot_burn_vs_issuance.py`
  or explicitly:
  `python src/analysis/plot_burn_vs_issuance.py --sample`
- Full (example):
  `python src/analysis/plot_burn_vs_issuance.py --panel data/processed/panels/daily_rollup_panel_v2.csv --issuance data/processed/issuance/issuance_daily.csv --tag full`
"""

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path


# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Locked protocol constant (docs/protocol.md).
DENCUN_DATE_UTC = date(2024, 3, 13)


OUTPUT_COLUMNS = [
    "date_utc",
    "issuance_eth",
    "rent_base_fee_burn_eth_sum",
    "rent_blob_fee_burn_eth_sum",
    "rent_total_burn_eth_sum",
    "issuance_minus_rent_burn_eth",
    "rollup_days",
    "base_burn_rollup_days",
    "blob_burn_rollup_days",
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


def _parse_float_optional(row: Row, key: str) -> float | None:
    v = row.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        raise SystemExit(f"Invalid type for {key!r}: expected string, got {type(v)}")
    s = v.strip()
    if s == "":
        return None
    try:
        out = float(s)
    except ValueError as exc:
        raise SystemExit(f"Invalid float for {key!r}: {s!r}") from exc
    if not math.isfinite(out):
        raise SystemExit(f"Non-finite value for {key!r}: {s!r}")
    return out


def load_csv_dict_rows(path: Path) -> tuple[list[str], list[Row]]:
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


def _validate_panel_required_columns(fieldnames: list[str]) -> None:
    required = {
        "date_utc",
        "rollup_id",
        "rent_base_fee_burn_eth",
        "rent_blob_fee_burn_eth",
    }
    missing = sorted(c for c in required if c not in set(fieldnames))
    if missing:
        raise SystemExit(f"Input panel is missing required columns: {missing}")


def _validate_issuance_required_columns(fieldnames: list[str]) -> None:
    required = {"date_utc", "issuance_eth"}
    missing = sorted(c for c in required if c not in set(fieldnames))
    if missing:
        raise SystemExit(f"Issuance series is missing required columns: {missing}")


def load_issuance_series(path: Path) -> tuple[dict[str, float], dict[str, list[str]]]:
    fieldnames, rows = load_csv_dict_rows(path)
    _validate_issuance_required_columns(fieldnames)

    issuance_by_date: dict[str, float] = {}
    sources: set[str] = set()
    methods: set[str] = set()
    for row in rows:
        date_str = _require_str(row, "date_utc")
        _parse_date_utc(date_str)  # validate
        issuance = _parse_float_required(row, "issuance_eth")
        if issuance < 0:
            raise SystemExit(
                "Negative issuance_eth detected while gross issuance mode is required. "
                f"date={date_str} issuance_eth={issuance}"
            )
        if date_str in issuance_by_date:
            raise SystemExit(f"Duplicate issuance date_utc: {date_str}")
        issuance_by_date[date_str] = issuance

        src = (row.get("source") or "").strip()
        if src:
            sources.add(src)
        method = (row.get("method") or "").strip()
        if method:
            methods.add(method)

    meta = {"sources": sorted(sources), "methods": sorted(methods)}
    return issuance_by_date, meta


@dataclass
class DailyBurnAccumulator:
    rent_base_fee_burn_eth_sum: float = 0.0
    rent_blob_fee_burn_eth_sum: float = 0.0
    rollup_days: int = 0
    base_burn_rollup_days: int = 0
    blob_burn_rollup_days: int = 0


def compute_daily_burn(rows: list[Row]) -> dict[str, DailyBurnAccumulator]:
    per_day: dict[str, DailyBurnAccumulator] = {}
    for row in rows:
        date_str = _require_str(row, "date_utc")
        _parse_date_utc(date_str)  # validate; ISO strings sort chronologically
        rollup_id = _require_str(row, "rollup_id")
        _ = rollup_id  # validated; used only for error context

        base_burn = _parse_float_optional(row, "rent_base_fee_burn_eth")
        blob_burn = _parse_float_optional(row, "rent_blob_fee_burn_eth")

        if base_burn is not None and base_burn < 0:
            raise SystemExit(f"Negative base burn not allowed: date_utc={date_str} rollup_id={rollup_id} value={base_burn}")
        if blob_burn is not None and blob_burn < 0:
            raise SystemExit(f"Negative blob burn not allowed: date_utc={date_str} rollup_id={rollup_id} value={blob_burn}")

        acc = per_day.get(date_str)
        if acc is None:
            acc = DailyBurnAccumulator()
            per_day[date_str] = acc

        acc.rollup_days += 1
        if base_burn is not None:
            acc.rent_base_fee_burn_eth_sum += float(base_burn)
            acc.base_burn_rollup_days += 1
        if blob_burn is not None:
            acc.rent_blob_fee_burn_eth_sum += float(blob_burn)
            acc.blob_burn_rollup_days += 1

    return per_day


def _fmt8(v: float) -> str:
    return f"{v:.8f}"


def build_daily_output_rows(
    *,
    burn_by_date: dict[str, DailyBurnAccumulator],
    issuance_by_date: dict[str, float],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for date_str in sorted(burn_by_date.keys()):
        issuance = issuance_by_date.get(date_str)
        if issuance is None:
            raise SystemExit(f"Missing issuance for date_utc={date_str} (provide --issuance or extend issuance input)")
        acc = burn_by_date[date_str]

        base_sum = float(acc.rent_base_fee_burn_eth_sum)
        blob_sum = float(acc.rent_blob_fee_burn_eth_sum)
        total_burn = base_sum + blob_sum
        issuance_minus = float(issuance) - total_burn

        out.append(
            {
                "date_utc": date_str,
                "issuance_eth": _fmt8(float(issuance)),
                "rent_base_fee_burn_eth_sum": _fmt8(base_sum),
                "rent_blob_fee_burn_eth_sum": _fmt8(blob_sum),
                "rent_total_burn_eth_sum": _fmt8(total_burn),
                # NOTE: this is issuance net of rollup-attributed burn only, not total Ethereum burn.
                "issuance_minus_rent_burn_eth": _fmt8(issuance_minus),
                "rollup_days": acc.rollup_days,
                "base_burn_rollup_days": acc.base_burn_rollup_days,
                "blob_burn_rollup_days": acc.blob_burn_rollup_days,
            }
        )
    return out


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    for i, r in enumerate(rows):
        missing = sorted(c for c in OUTPUT_COLUMNS if c not in r)
        if missing:
            raise SystemExit(f"Output row missing columns at idx={i}: {missing}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(OUTPUT_COLUMNS), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in OUTPUT_COLUMNS})


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


def _svg_two_panel_burn_vs_issuance(
    *,
    width: int,
    height: int,
    xs: list[int],
    issuance_eth: list[float],
    burn_base_eth: list[float],
    burn_blob_eth: list[float],
    dencun_x: int | None,
    title: str,
) -> str:
    if not xs:
        raise ValueError("empty series")
    if len(xs) != len(issuance_eth) or len(xs) != len(burn_base_eth) or len(xs) != len(burn_blob_eth):
        raise ValueError("series length mismatch")

    margin_left = 70
    margin_right = 20
    margin_top = 40
    margin_bottom = 40
    gap = 40
    plot_w = width - margin_left - margin_right
    avail_h = height - margin_top - margin_bottom - gap
    if avail_h <= 0:
        raise ValueError("invalid height")
    top_h = int(round(avail_h * 0.6))
    bot_h = avail_h - top_h
    top_y = margin_top
    bot_y = margin_top + top_h + gap

    x_min = min(xs)
    x_max = max(xs)
    if x_min == x_max:
        x_min -= 1
        x_max += 1

    def x_px(x: int) -> float:
        return margin_left + plot_w * ((x - x_min) / float(x_max - x_min))

    # Top panel y-scale (issuance).
    top_vals = [v for v in issuance_eth if math.isfinite(v)]
    if not top_vals:
        raise ValueError("no finite issuance values")
    top_min = min(top_vals)
    top_max = max(top_vals)
    if top_min == top_max:
        top_min -= 1.0
        top_max += 1.0
    top_pad = 0.05 * (top_max - top_min)
    top_y0 = top_min - top_pad
    top_y1 = top_max + top_pad

    def y_top_px(y: float) -> float:
        return top_y + top_h * (1.0 - ((y - top_y0) / float(top_y1 - top_y0)))

    # Bottom panel y-scale (burn).
    burn_vals = [v for v in burn_base_eth + burn_blob_eth if math.isfinite(v)]
    if not burn_vals:
        raise ValueError("no finite burn values")
    bot_max = max(burn_vals)
    if bot_max <= 0:
        bot_max = 1.0
    bot_y0 = 0.0
    bot_y1 = bot_max * 1.1

    def y_bot_px(y: float) -> float:
        return bot_y + bot_h * (1.0 - ((y - bot_y0) / float(bot_y1 - bot_y0)))

    # Dencun marker line spans both panels.
    dencun_line = ""
    dencun_label = ""
    if dencun_x is not None and x_min <= dencun_x <= x_max:
        xline = x_px(dencun_x)
        y1 = top_y
        y2 = bot_y + bot_h
        dencun_line = (
            f'<line x1="{xline:.2f}" y1="{y1}" x2="{xline:.2f}" y2="{y2}" '
            'stroke="#d97706" stroke-width="2" stroke-dasharray="6 6" />'
        )
        dencun_label = (
            f'<text x="{xline+6:.2f}" y="{top_y+14}" font-size="11" fill="#92400e">Dencun (2024-03-13)</text>'
        )

    def y_ticks(y0: float, y1: float, *, y_fn, x0: int, n: int) -> list[str]:
        elems: list[str] = []
        for i in range(n + 1):
            yv = y0 + (y1 - y0) * (i / float(n))
            yp = y_fn(yv)
            elems.append(f'<line x1="{x0-5}" y1="{yp:.2f}" x2="{x0}" y2="{yp:.2f}" stroke="#333" />')
            elems.append(
                f'<text x="{x0-8}" y="{yp+4:.2f}" font-size="11" text-anchor="end" fill="#111">{yv:.1f}</text>'
            )
        return elems

    def polyline(color: str, *, ys: list[float], y_fn) -> list[str]:
        segs = _segment_points(xs, ys)
        out: list[str] = []
        for seg in segs:
            if len(seg) < 2:
                continue
            pts = " ".join(f"{x_px(x):.2f},{y_fn(y):.2f}" for x, y in seg)
            out.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{pts}" />')
        return out

    legend = "\n".join(
        [
            f'<rect x="{margin_left+10}" y="10" width="10" height="10" fill="#2563eb" />',
            f'<text x="{margin_left+25}" y="19" font-size="12" fill="#111">gross issuance (ETH/day)</text>',
            f'<rect x="{margin_left+190}" y="10" width="10" height="10" fill="#dc2626" />',
            f'<text x="{margin_left+205}" y="19" font-size="12" fill="#111">base fee burn (rollup-attributed)</text>',
            f'<rect x="{margin_left+410}" y="10" width="10" height="10" fill="#16a34a" />',
            f'<text x="{margin_left+425}" y="19" font-size="12" fill="#111">blob fee burn (rollup-attributed)</text>',
            f'<line x1="{margin_left+650}" y1="15" x2="{margin_left+680}" y2="15" stroke="#d97706" stroke-width="2" stroke-dasharray="6 6" />',
            f'<text x="{margin_left+690}" y="19" font-size="12" fill="#111">Dencun</text>',
        ]
    )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect x="0" y="0" width="100%" height="100%" fill="white" />',
            f'<text x="{margin_left}" y="34" font-size="14" fill="#111">{title}</text>',
            legend,
            # Top axes
            f'<line x1="{margin_left}" y1="{top_y}" x2="{margin_left}" y2="{top_y + top_h}" stroke="#111" />',
            f'<line x1="{margin_left}" y1="{top_y + top_h}" x2="{margin_left + plot_w}" y2="{top_y + top_h}" stroke="#111" />',
            *y_ticks(top_y0, top_y1, y_fn=y_top_px, x0=margin_left, n=5),
            f'<text x="{margin_left}" y="{top_y-8}" font-size="12" fill="#111">Issuance</text>',
            # Bottom axes
            f'<line x1="{margin_left}" y1="{bot_y}" x2="{margin_left}" y2="{bot_y + bot_h}" stroke="#111" />',
            f'<line x1="{margin_left}" y1="{bot_y + bot_h}" x2="{margin_left + plot_w}" y2="{bot_y + bot_h}" stroke="#111" />',
            *y_ticks(bot_y0, bot_y1, y_fn=y_bot_px, x0=margin_left, n=5),
            f'<text x="{margin_left}" y="{bot_y-8}" font-size="12" fill="#111">Burn (rollup-attributed)</text>',
            dencun_line,
            dencun_label,
            *polyline("#2563eb", ys=issuance_eth, y_fn=y_top_px),
            *polyline("#dc2626", ys=burn_base_eth, y_fn=y_bot_px),
            *polyline("#16a34a", ys=burn_blob_eth, y_fn=y_bot_px),
            "</svg>",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plot_burn_vs_issuance.py")
    p.add_argument("--sample", action="store_true", help="Use committed sample inputs (default if --panel is not set)")
    p.add_argument("--panel", default=None, help="Path to a daily_rollup_panel v2 CSV")
    p.add_argument("--issuance", default=None, help="Path to a daily issuance CSV (date_utc, issuance_eth, ...)")
    p.add_argument("--tag", default=None, help="Output tag suffix (default: sample/full)")
    return p


def main(argv: list[str]) -> None:
    root = _repo_root()
    args = build_parser().parse_args(argv[1:])

    if args.panel is not None and args.sample:
        raise SystemExit("Use either --sample (or default) OR --panel, not both")

    if args.panel is None:
        # Sample mode is the default.
        panel_abs = root / "data/samples/panels/daily_rollup_panel_v2_sample.csv"
        issuance_abs = root / "data/samples/issuance/issuance_daily_sample.csv" if args.issuance is None else (root / args.issuance)
        tag = args.tag or "sample"
    else:
        panel_path = Path(args.panel)
        panel_abs = panel_path if panel_path.is_absolute() else (root / panel_path)
        issuance_abs = None if args.issuance is None else (Path(args.issuance) if Path(args.issuance).is_absolute() else (root / args.issuance))
        tag = args.tag or "full"

    if not panel_abs.exists():
        raise SystemExit(f"panel not found: {panel_abs}")
    panel_rel = str(_ensure_within_repo(root, panel_abs.resolve()))
    panel_sha = _sha256_file(panel_abs)

    issuance_by_date: dict[str, float] = {}
    issuance_meta: dict[str, list[str]] = {"sources": [], "methods": []}
    issuance_rel = None
    issuance_sha = None
    issuance_bytes = None

    if issuance_abs is not None:
        if not issuance_abs.exists():
            raise SystemExit(f"issuance series not found: {issuance_abs}")
        issuance_rel = str(_ensure_within_repo(root, issuance_abs.resolve()))
        issuance_sha = _sha256_file(issuance_abs)
        issuance_bytes = issuance_abs.stat().st_size
        issuance_by_date, issuance_meta = load_issuance_series(issuance_abs)

    fieldnames, rows = load_csv_dict_rows(panel_abs)
    _validate_panel_required_columns(fieldnames)
    burn_by_date = compute_daily_burn(rows)

    # Panel-provided issuance (if present and no external issuance provided).
    if not issuance_by_date:
        if "issuance_eth" not in set(fieldnames):
            raise SystemExit("Missing issuance series: provide --issuance (or ensure panel has issuance_eth)")

        per_date_vals: dict[str, float] = {}
        for row in rows:
            date_str = _require_str(row, "date_utc")
            issuance_text = (row.get("issuance_eth") or "").strip()
            if issuance_text == "":
                continue
            try:
                v = float(issuance_text)
            except ValueError as exc:
                raise SystemExit(f"Invalid issuance_eth in panel for date_utc={date_str}: {issuance_text!r}") from exc
            if not math.isfinite(v):
                raise SystemExit(f"Non-finite issuance_eth in panel for date_utc={date_str}: {issuance_text!r}")
            if date_str in per_date_vals and abs(per_date_vals[date_str] - v) > 1e-9:
                raise SystemExit(f"Inconsistent issuance_eth within date_utc={date_str} (panel duplicates)")
            per_date_vals[date_str] = v

        if not per_date_vals:
            raise SystemExit("Missing issuance series: panel issuance_eth is empty; provide --issuance")
        issuance_by_date = per_date_vals

    out_rows = build_daily_output_rows(burn_by_date=burn_by_date, issuance_by_date=issuance_by_date)

    tables_dir = root / "reports/tables"
    figs_dir = root / "reports/figures"
    out_csv = tables_dir / f"burn_vs_issuance_{tag}.csv"
    out_svg = figs_dir / f"burn_vs_issuance_{tag}.svg"
    out_run = tables_dir / f"burn_vs_issuance_{tag}_run.json"

    _write_csv(out_csv, out_rows)

    dates: list[date] = [_parse_date_utc(str(r["date_utc"])) for r in out_rows]
    xs: list[int] = list(range(len(out_rows)))
    issuance_series: list[float] = [float(r["issuance_eth"]) for r in out_rows]
    burn_base_series: list[float] = [float(r["rent_base_fee_burn_eth_sum"]) for r in out_rows]
    burn_blob_series: list[float] = [float(r["rent_blob_fee_burn_eth_sum"]) for r in out_rows]

    dencun_idx = next((i for i, d in enumerate(dates) if d >= DENCUN_DATE_UTC), None)

    title = f"Rollup-attributed burn vs gross ETH issuance — {tag}"
    svg = _svg_two_panel_burn_vs_issuance(
        width=900,
        height=520,
        xs=xs,
        issuance_eth=issuance_series,
        burn_base_eth=burn_base_series,
        burn_blob_eth=burn_blob_series,
        dencun_x=dencun_idx,
        title=title,
    )
    _write_text(out_svg, svg)

    now = datetime.now(timezone.utc).isoformat()
    run_manifest: dict[str, object] = {
        "created_at_utc": now,
        "script_path": str(_ensure_within_repo(root, Path(__file__).resolve())),
        "git_sha": _git_sha(root),
        "command": " ".join(json.dumps(t) for t in sys.argv),
        "protocol": {
            "dencun_date_utc": DENCUN_DATE_UTC.isoformat(),
            "issuance_definition": "gross consensus-layer issuance to validators (not net of burn)",
            "burn_components": [
                "rent_base_fee_burn_eth (execution base fee burn; rollup-attributed)",
                "rent_blob_fee_burn_eth (blob fee burn; rollup-attributed; post-Dencun only)",
            ],
            "notes": "Burn series here is rollup-attributed (sum over rollups in the panel), not total Ethereum burn.",
        },
        "inputs": [
            {"path": panel_rel, "sha256": panel_sha, "bytes": panel_abs.stat().st_size},
        ],
        "outputs": [
            {"path": str(_ensure_within_repo(root, out_csv)), "sha256": _sha256_file(out_csv), "bytes": out_csv.stat().st_size},
            {"path": str(_ensure_within_repo(root, out_svg)), "sha256": _sha256_file(out_svg), "bytes": out_svg.stat().st_size},
        ],
    }
    if issuance_rel is not None and issuance_sha is not None and issuance_bytes is not None:
        run_manifest["inputs"].append({"path": issuance_rel, "sha256": issuance_sha, "bytes": issuance_bytes})
        run_manifest["protocol"] = dict(run_manifest["protocol"])  # shallow copy
        run_manifest["protocol"]["issuance_meta"] = issuance_meta

    out_run.parent.mkdir(parents=True, exist_ok=True)
    out_run.write_text(json.dumps(run_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "tag": tag,
                "outputs": [
                    str(_ensure_within_repo(root, out_csv)),
                    str(_ensure_within_repo(root, out_svg)),
                    str(_ensure_within_repo(root, out_run)),
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main(sys.argv)
