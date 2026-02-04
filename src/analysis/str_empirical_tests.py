from __future__ import annotations

"""Empirical STR tests (trend, break, elasticity) with deterministic sample mode.

Inputs (sample mode):
- `data/samples/panels/daily_rollup_panel_v1_sample.csv`

Inputs (full mode):
- `--panel <path>` pointing to a contract-v1 `daily_rollup_panel` CSV (see `contracts/schemas/panel_schema_str_v1.yaml`)

Outputs (stable names):
- `reports/tables/str_empirical_tests_<tag>.json`
- `reports/tables/str_empirical_tests_<tag>.md`
- `reports/tables/str_time_series_<tag>.csv`
- `reports/figures/str_time_series_<tag>.svg`
- `reports/tables/str_empirical_tests_<tag>_run.json` (traceability: timestamp, command, versions, hashes)

How to run:
- Sample:
  `python src/analysis/str_empirical_tests.py --sample`
- Full (example):
  `python src/analysis/str_empirical_tests.py --panel data/processed/panels/daily_rollup_panel_v1.csv --tag full`
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

from src.analysis.metrics_str import compute_daily_ecosystem_str, load_panel_csv  # noqa: E402


DENCUN_DATE_UTC = date(2024, 3, 13)  # per docs/protocol.md


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


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _two_sided_p_normal(z: float) -> float:
    return max(0.0, min(1.0, 2.0 * (1.0 - _normal_cdf(abs(z)))))


def _mean(xs: list[float]) -> float:
    if not xs:
        raise ValueError("mean of empty list")
    return sum(xs) / float(len(xs))


def _outer(a: list[float], b: list[float]) -> list[list[float]]:
    return [[ai * bj for bj in b] for ai in a]


def _matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    if not a or not b:
        raise ValueError("empty matrix")
    n = len(a)
    m = len(a[0])
    if any(len(row) != m for row in a):
        raise ValueError("ragged matrix a")
    if any(len(row) != len(b[0]) for row in b):
        raise ValueError("ragged matrix b")
    if len(b) != m:
        raise ValueError("dimension mismatch")

    p = len(b[0])
    out = [[0.0 for _ in range(p)] for _ in range(n)]
    for i in range(n):
        for k in range(m):
            aik = a[i][k]
            if aik == 0.0:
                continue
            for j in range(p):
                out[i][j] += aik * b[k][j]
    return out


def _matvec(a: list[list[float]], v: list[float]) -> list[float]:
    if not a:
        raise ValueError("empty matrix")
    m = len(a[0])
    if any(len(row) != m for row in a):
        raise ValueError("ragged matrix")
    if len(v) != m:
        raise ValueError("dimension mismatch")
    return [sum(aij * vj for aij, vj in zip(row, v, strict=True)) for row in a]


def _transpose(a: list[list[float]]) -> list[list[float]]:
    if not a:
        return []
    m = len(a[0])
    if any(len(row) != m for row in a):
        raise ValueError("ragged matrix")
    return [[a[i][j] for i in range(len(a))] for j in range(m)]


def _invert(a: list[list[float]]) -> list[list[float]]:
    n = len(a)
    if n == 0 or any(len(row) != n for row in a):
        raise ValueError("matrix must be square")

    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("singular matrix")
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]

        piv = aug[col][col]
        aug[col] = [x / piv for x in aug[col]]

        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            if factor == 0.0:
                continue
            aug[r] = [rv - factor * cv for rv, cv in zip(aug[r], aug[col], strict=True)]

    return [row[n:] for row in aug]


@dataclass(frozen=True)
class OlsResult:
    beta: list[float]
    residuals: list[float]
    xtx_inv: list[list[float]]
    r2: float


def ols_fit(y: list[float], x: list[list[float]]) -> OlsResult:
    if len(y) != len(x):
        raise ValueError("y and x length mismatch")
    if not y:
        raise ValueError("empty regression")
    k = len(x[0])
    if any(len(row) != k for row in x):
        raise ValueError("ragged x")

    xt = _transpose(x)
    xtx = _matmul(xt, x)
    xtx_inv = _invert(xtx)
    xty = _matvec(xt, y)
    beta = _matvec(xtx_inv, xty)

    y_hat = [sum(bj * xij for bj, xij in zip(beta, xi, strict=True)) for xi in x]
    residuals = [yi - yhi for yi, yhi in zip(y, y_hat, strict=True)]

    y_bar = _mean(y)
    sse = sum(e * e for e in residuals)
    sst = sum((yi - y_bar) ** 2 for yi in y)
    r2 = 1.0 - (sse / sst) if sst > 0 else float("nan")

    return OlsResult(beta=beta, residuals=residuals, xtx_inv=xtx_inv, r2=r2)


def newey_west_covariance(x: list[list[float]], residuals: list[float], xtx_inv: list[list[float]], *, lags: int) -> list[list[float]]:
    n = len(x)
    if n == 0 or len(residuals) != n:
        raise ValueError("empty or mismatched inputs")
    if lags < 0:
        raise ValueError("lags must be >= 0")

    k = len(x[0])
    s = [[0.0 for _ in range(k)] for _ in range(k)]

    for t in range(n):
        ut = residuals[t]
        xt = x[t]
        o = _outer(xt, xt)
        for i in range(k):
            for j in range(k):
                s[i][j] += (ut * ut) * o[i][j]

    for lag in range(1, lags + 1):
        w = 1.0 - (lag / float(lags + 1))
        for t in range(lag, n):
            ut = residuals[t]
            ul = residuals[t - lag]
            xt = x[t]
            xl = x[t - lag]
            cross = w * ut * ul
            o1 = _outer(xt, xl)
            o2 = _outer(xl, xt)
            for i in range(k):
                for j in range(k):
                    s[i][j] += cross * (o1[i][j] + o2[i][j])

    v = _matmul(_matmul(xtx_inv, s), xtx_inv)
    return v


def _nw_default_lags(n: int) -> int:
    # Common NW rule of thumb: floor(4 * (n/100)^(2/9)).
    if n <= 0:
        return 0
    return max(0, int(math.floor(4.0 * ((n / 100.0) ** (2.0 / 9.0)))))


def mann_kendall_test(y: list[float]) -> dict[str, float]:
    n = len(y)
    if n < 2:
        return {"n": float(n), "s": 0.0, "tau": float("nan"), "z": float("nan"), "p_value": float("nan")}

    s = 0
    for i in range(n - 1):
        yi = y[i]
        for j in range(i + 1, n):
            d = y[j] - yi
            if d > 0:
                s += 1
            elif d < 0:
                s -= 1

    # Tie correction
    counts: dict[float, int] = {}
    for v in y:
        counts[v] = counts.get(v, 0) + 1
    tie_term = sum(t * (t - 1) * (2 * t + 5) for t in counts.values() if t > 1)
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var_s <= 0:
        z = 0.0
    else:
        if s > 0:
            z = (s - 1) / math.sqrt(var_s)
        elif s < 0:
            z = (s + 1) / math.sqrt(var_s)
        else:
            z = 0.0

    denom = 0.5 * n * (n - 1)
    tau = (s / denom) if denom > 0 else float("nan")
    p = _two_sided_p_normal(z)
    return {"n": float(n), "s": float(s), "tau": float(tau), "z": float(z), "p_value": float(p)}


def _write_csv(path: Path, rows: list[dict[str, object]], *, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _svg_line_chart(
    *,
    width: int,
    height: int,
    xs: list[int],
    ys: list[float],
    dencun_x: int | None,
    title: str,
) -> str:
    if len(xs) != len(ys):
        raise ValueError("xs/ys length mismatch")
    if not xs:
        raise ValueError("empty chart series")

    margin_left = 60
    margin_right = 20
    margin_top = 30
    margin_bottom = 40
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    y_min = min(ys)
    y_max = max(ys)
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

    points = " ".join(f"{x_px(x):.2f},{y_px(y):.2f}" for x, y in zip(xs, ys, strict=True))

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

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect x="0" y="0" width="100%" height="100%" fill="white" />',
            f'<text x="{margin_left}" y="20" font-size="14" fill="#111">{title}</text>',
            # Axes
            f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#111" />',
            f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" stroke="#111" />',
            *tick_elems,
            dencun_line,
            f'<polyline fill="none" stroke="#2563eb" stroke-width="2.5" points="{points}" />',
            "</svg>",
        ]
    )


def main(argv: list[str]) -> None:
    root = _repo_root()

    p = argparse.ArgumentParser(prog="str_empirical_tests.py")
    p.add_argument("--sample", action="store_true", help="Use the committed sample panel")
    p.add_argument("--panel", default=None, help="Path to a daily_rollup_panel v1 CSV")
    p.add_argument("--tag", default=None, help="Output tag suffix (default: sample/full)")
    p.add_argument("--nw-lags", type=int, default=None, help="Newey-West lags (default: rule-of-thumb)")
    args = p.parse_args(argv[1:])

    if args.sample:
        panel_path = root / "data/samples/panels/daily_rollup_panel_v1_sample.csv"
        tag = args.tag or "sample"
    else:
        if args.panel is None:
            raise SystemExit("Missing --panel (or use --sample)")
        panel_path = Path(args.panel)
        tag = args.tag or "full"

    if not panel_path.exists():
        raise SystemExit(f"panel not found: {panel_path}")

    panel_rel = str(_ensure_within_repo(root, panel_path.resolve()))
    panel_sha = _sha256_file(panel_path)

    rows = load_panel_csv(panel_path)
    daily = compute_daily_ecosystem_str(rows)

    dates: list[date] = [_parse_date_utc(r.date_utc) for r in daily]
    y_str: list[float] = [r.str_value for r in daily]
    fees_sum: list[float] = [r.l2_fees_eth_sum for r in daily]
    rent_sum: list[float] = [r.rent_paid_eth_sum for r in daily]
    t_idx: list[int] = list(range(len(daily)))

    dencun_idx = next((i for i, d in enumerate(dates) if d >= DENCUN_DATE_UTC), None)
    post = [1.0 if d >= DENCUN_DATE_UTC else 0.0 for d in dates]

    lags = args.nw_lags if args.nw_lags is not None else _nw_default_lags(len(y_str))

    mk = mann_kendall_test(y_str)

    # Trend regression: STR ~ 1 + t
    x_trend = [[1.0, float(t)] for t in t_idx]
    trend_fit = ols_fit(y_str, x_trend)
    trend_cov = newey_west_covariance(x_trend, trend_fit.residuals, trend_fit.xtx_inv, lags=lags)
    trend_se = [math.sqrt(max(0.0, trend_cov[i][i])) for i in range(len(trend_fit.beta))]
    slope = trend_fit.beta[1]
    slope_se = trend_se[1]
    slope_t = slope / slope_se if slope_se > 0 else float("nan")
    slope_p = _two_sided_p_normal(slope_t)

    # Break regression (mean shift): STR ~ 1 + post
    x_break_mean = [[1.0, float(pv)] for pv in post]
    break_mean_fit = ols_fit(y_str, x_break_mean)
    break_mean_cov = newey_west_covariance(x_break_mean, break_mean_fit.residuals, break_mean_fit.xtx_inv, lags=lags)
    break_mean_se = [math.sqrt(max(0.0, break_mean_cov[i][i])) for i in range(len(break_mean_fit.beta))]
    shift = break_mean_fit.beta[1]
    shift_se = break_mean_se[1]
    shift_t = shift / shift_se if shift_se > 0 else float("nan")
    shift_p = _two_sided_p_normal(shift_t)

    # Break regression (mean + slope change): STR ~ 1 + t + post + post*t
    x_break_trend = [[1.0, float(t), float(pv), float(pv) * float(t)] for t, pv in zip(t_idx, post, strict=True)]
    break_trend_fit = ols_fit(y_str, x_break_trend)
    break_trend_cov = newey_west_covariance(x_break_trend, break_trend_fit.residuals, break_trend_fit.xtx_inv, lags=lags)
    break_trend_se = [math.sqrt(max(0.0, break_trend_cov[i][i])) for i in range(len(break_trend_fit.beta))]

    shift2 = break_trend_fit.beta[2]
    shift2_se = break_trend_se[2]
    shift2_t = shift2 / shift2_se if shift2_se > 0 else float("nan")
    shift2_p = _two_sided_p_normal(shift2_t)

    slope_change = break_trend_fit.beta[3]
    slope_change_se = break_trend_se[3]
    slope_change_t = slope_change / slope_change_se if slope_change_se > 0 else float("nan")
    slope_change_p = _two_sided_p_normal(slope_change_t)

    # Elasticity regression (daily aggregates): log(rent) ~ 1 + log(fees) + log(txcount) + post
    txcount_sum_by_date: dict[str, float] = {}
    for row in rows:
        d = row.get("date_utc", "").strip()
        if d == "":
            continue
        tx_raw = (row.get("txcount") or "").strip()
        if tx_raw == "":
            continue
        try:
            tx = float(int(tx_raw))
        except ValueError:
            continue
        txcount_sum_by_date[d] = txcount_sum_by_date.get(d, 0.0) + tx

    y_log_rent: list[float] = []
    x_elast: list[list[float]] = []
    elast_dates: list[str] = []
    for d, fsum, rsum, pv in zip(dates, fees_sum, rent_sum, post, strict=True):
        d_str = d.isoformat()
        txsum = txcount_sum_by_date.get(d_str)
        if txsum is None:
            continue
        if fsum <= 0 or rsum <= 0 or txsum <= 0:
            continue
        y_log_rent.append(math.log(rsum))
        x_elast.append([1.0, math.log(fsum), math.log(txsum), float(pv)])
        elast_dates.append(d_str)

    elast_fit = ols_fit(y_log_rent, x_elast)
    elast_cov = newey_west_covariance(x_elast, elast_fit.residuals, elast_fit.xtx_inv, lags=_nw_default_lags(len(y_log_rent)))
    elast_se = [math.sqrt(max(0.0, elast_cov[i][i])) for i in range(len(elast_fit.beta))]

    coef_log_fees = elast_fit.beta[1]
    coef_log_fees_se = elast_se[1]
    coef_log_fees_t = coef_log_fees / coef_log_fees_se if coef_log_fees_se > 0 else float("nan")
    coef_log_fees_p = _two_sided_p_normal(coef_log_fees_t)

    coef_log_tx = elast_fit.beta[2]
    coef_log_tx_se = elast_se[2]
    coef_log_tx_t = coef_log_tx / coef_log_tx_se if coef_log_tx_se > 0 else float("nan")
    coef_log_tx_p = _two_sided_p_normal(coef_log_tx_t)

    coef_post = elast_fit.beta[3]
    coef_post_se = elast_se[3]
    coef_post_t = coef_post / coef_post_se if coef_post_se > 0 else float("nan")
    coef_post_p = _two_sided_p_normal(coef_post_t)

    pre = [v for d, v in zip(dates, y_str, strict=True) if d < DENCUN_DATE_UTC]
    post_vals = [v for d, v in zip(dates, y_str, strict=True) if d >= DENCUN_DATE_UTC]

    result = {
        "ok": True,
        "inputs": {
            "panel_path": panel_rel,
            "panel_sha256": panel_sha,
            "n_days": len(y_str),
            "date_min_utc": dates[0].isoformat() if dates else None,
            "date_max_utc": dates[-1].isoformat() if dates else None,
            "dencun_date_utc": DENCUN_DATE_UTC.isoformat(),
            "dencun_index": dencun_idx,
        },
        "summary": {
            "str_mean_pre": _mean(pre) if pre else float("nan"),
            "str_mean_post": _mean(post_vals) if post_vals else float("nan"),
            "str_mean_all": _mean(y_str) if y_str else float("nan"),
            "str_min": min(y_str) if y_str else float("nan"),
            "str_max": max(y_str) if y_str else float("nan"),
        },
        "tests": {
            "mann_kendall_trend": mk,
            "newey_west_trend_regression": {
                "lags": lags,
                "beta_intercept": trend_fit.beta[0],
                "beta_time": slope,
                "se_time": slope_se,
                "t_time": slope_t,
                "p_time_normal_approx": slope_p,
                "r2": trend_fit.r2,
            },
            "dencun_break_mean_shift": {
                "lags": lags,
                "beta_post": shift,
                "se_post": shift_se,
                "t_post": shift_t,
                "p_post_normal_approx": shift_p,
                "r2": break_mean_fit.r2,
            },
            "dencun_break_trend_change": {
                "lags": lags,
                "beta_post_level": shift2,
                "se_post_level": shift2_se,
                "t_post_level": shift2_t,
                "p_post_level_normal_approx": shift2_p,
                "beta_post_slope": slope_change,
                "se_post_slope": slope_change_se,
                "t_post_slope": slope_change_t,
                "p_post_slope_normal_approx": slope_change_p,
                "r2": break_trend_fit.r2,
            },
            "elasticity_log_rent_controls": {
                "n_obs": len(y_log_rent),
                "lags": _nw_default_lags(len(y_log_rent)),
                "beta_log_fees": coef_log_fees,
                "se_log_fees": coef_log_fees_se,
                "t_log_fees": coef_log_fees_t,
                "p_log_fees_normal_approx": coef_log_fees_p,
                "beta_log_txcount": coef_log_tx,
                "se_log_txcount": coef_log_tx_se,
                "t_log_txcount": coef_log_tx_t,
                "p_log_txcount_normal_approx": coef_log_tx_p,
                "beta_post": coef_post,
                "se_post": coef_post_se,
                "t_post": coef_post_t,
                "p_post_normal_approx": coef_post_p,
                "r2": elast_fit.r2,
            },
        },
        "notes": [
            "P-values use a normal approximation (stdlib-only, no external stats deps).",
            "Newey–West HAC is implemented for time-ordered daily aggregates; interpret panel-style controls cautiously.",
        ],
    }

    tables_dir = root / "reports/tables"
    figs_dir = root / "reports/figures"

    out_json = tables_dir / f"str_empirical_tests_{tag}.json"
    out_md = tables_dir / f"str_empirical_tests_{tag}.md"
    out_csv = tables_dir / f"str_time_series_{tag}.csv"
    out_svg = figs_dir / f"str_time_series_{tag}.svg"
    out_run = tables_dir / f"str_empirical_tests_{tag}_run.json"

    _write_json(out_json, result)

    md = "\n".join(
        [
            f"# STR empirical tests ({tag})",
            "",
            "## Inputs",
            f"- Panel: `{panel_rel}`",
            f"- Panel sha256: `{panel_sha}`",
            f"- Dencun boundary (UTC): `{DENCUN_DATE_UTC.isoformat()}`",
            "",
            "## Summary (ecosystem STR)",
            f"- Mean STR (pre): {result['summary']['str_mean_pre']:.4f}",
            f"- Mean STR (post): {result['summary']['str_mean_post']:.4f}",
            f"- Min/Max STR: {result['summary']['str_min']:.4f} / {result['summary']['str_max']:.4f}",
            "",
            "## Tests",
            f"- Mann–Kendall tau: {mk['tau']:.4f}, p≈{mk['p_value']:.4g}",
            f"- NW trend slope (STR/day): {slope:.6f} (se {slope_se:.6f}), p≈{slope_p:.4g}",
            f"- Break (mean shift at Dencun): {shift:.4f} (se {shift_se:.4f}), p≈{shift_p:.4g}",
            f"- Break (post slope change): {slope_change:.6f} (se {slope_change_se:.6f}), p≈{slope_change_p:.4g}",
            f"- Elasticity log(rent)~log(fees): {coef_log_fees:.3f} (se {coef_log_fees_se:.3f}), p≈{coef_log_fees_p:.4g}",
            "",
            "## Outputs",
            f"- `{str(_ensure_within_repo(root, out_json))}`",
            f"- `{str(_ensure_within_repo(root, out_md))}`",
            f"- `{str(_ensure_within_repo(root, out_csv))}`",
            f"- `{str(_ensure_within_repo(root, out_svg))}`",
            f"- `{str(_ensure_within_repo(root, out_run))}` (run manifest)",
            "",
            "Notes:",
            "- P-values are normal approximations (see JSON for details).",
        ]
    )
    _write_text(out_md, md)

    # Time series CSV
    ts_rows = []
    for d, yv, fs, rs in zip(dates, y_str, fees_sum, rent_sum, strict=True):
        ts_rows.append(
            {
                "date_utc": d.isoformat(),
                "str": f"{yv:.10f}",
                "l2_fees_eth_sum": f"{fs:.8f}",
                "rent_paid_eth_sum": f"{rs:.8f}",
            }
        )
    _write_csv(out_csv, ts_rows, fieldnames=["date_utc", "str", "l2_fees_eth_sum", "rent_paid_eth_sum"])

    # SVG chart (STR series)
    svg = _svg_line_chart(
        width=900,
        height=420,
        xs=t_idx,
        ys=y_str,
        dencun_x=dencun_idx,
        title=f"Ecosystem STR (daily) — {tag}",
    )
    _write_text(out_svg, svg)

    # Run manifest (traceability)
    now = datetime.now(timezone.utc).isoformat()
    run_manifest = {
        "created_at_utc": now,
        "script_path": str(_ensure_within_repo(root, Path(__file__).resolve())),
        "git_sha": _git_sha(root),
        "command": " ".join(json.dumps(t) for t in sys.argv),
        "inputs": [
            {"path": panel_rel, "sha256": panel_sha, "bytes": panel_path.stat().st_size},
        ],
        "outputs": [
            {"path": str(_ensure_within_repo(root, out_json)), "sha256": _sha256_file(out_json), "bytes": out_json.stat().st_size},
            {"path": str(_ensure_within_repo(root, out_md)), "sha256": _sha256_file(out_md), "bytes": out_md.stat().st_size},
            {"path": str(_ensure_within_repo(root, out_csv)), "sha256": _sha256_file(out_csv), "bytes": out_csv.stat().st_size},
            {"path": str(_ensure_within_repo(root, out_svg)), "sha256": _sha256_file(out_svg), "bytes": out_svg.stat().st_size},
        ],
    }
    _write_json(out_run, run_manifest)

    print(json.dumps({"ok": True, "tag": tag, "outputs": [str(out_json), str(out_md), str(out_csv), str(out_svg), str(out_run)]}, indent=2))


def _parse_date_utc(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid date_utc (expected YYYY-MM-DD): {value!r}") from exc


if __name__ == "__main__":
    main(sys.argv)
