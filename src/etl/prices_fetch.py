from __future__ import annotations

"""Prices ETL (stdlib-only).

Modes:
- `--sample`: generate deterministic ETH/USD daily closes for the canonical sample
  window (2024-02-20..2024-04-30).
- snapshot mode (default when `--sample` is not used): fetch CoinGecko market chart
  data or load a saved raw snapshot, normalize to daily closes, and write CSV.

Required output columns are always asserted: `date_utc`, `eth_usd_close`.
"""

import argparse
import csv
import json
import math
import os
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_COLUMNS = ("date_utc", "eth_usd_close")
PROTOCOL_START_DATE = date(2022, 1, 1)
SAMPLE_WINDOW_START = date(2024, 2, 20)
SAMPLE_WINDOW_END = date(2024, 4, 30)

COINGECKO_MARKET_CHART_BASE = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"


def _parse_date(value: str, *, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {label} date (expected YYYY-MM-DD): {value!r}") from exc


def _iter_dates(start: date, end: date) -> list[date]:
    if end < start:
        raise SystemExit(f"end date must be >= start date (start={start.isoformat()}, end={end.isoformat()})")
    out: list[date] = []
    d = start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def _coerce_finite_float(value: str, *, label: str) -> float:
    try:
        out = float(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid numeric {label}: {value!r}") from exc
    if not math.isfinite(out):
        raise SystemExit(f"Invalid non-finite {label}: {value!r}")
    return out


def _assert_required_rows(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise SystemExit("No rows to write after normalization")

    seen_dates: set[str] = set()
    for i, row in enumerate(rows, start=1):
        missing = [c for c in REQUIRED_COLUMNS if c not in row]
        if missing:
            raise SystemExit(f"row {i} missing required columns: {missing}")

        raw_date = (row.get("date_utc") or "").strip()
        if raw_date == "":
            raise SystemExit(f"row {i}: empty date_utc")
        parsed = _parse_date(raw_date, label="date_utc")
        if parsed.isoformat() != raw_date:
            raise SystemExit(f"row {i}: date_utc must be ISO YYYY-MM-DD, got {raw_date!r}")

        if raw_date in seen_dates:
            raise SystemExit(f"row {i}: duplicate date_utc: {raw_date}")
        seen_dates.add(raw_date)

        close = (row.get("eth_usd_close") or "").strip()
        if close == "":
            raise SystemExit(f"row {i}: empty eth_usd_close")
        value = _coerce_finite_float(close, label="eth_usd_close")
        if value <= 0:
            raise SystemExit(f"row {i}: eth_usd_close must be > 0, got {close!r}")


def _write_csv_rows(*, path: Path, rows: list[dict[str, str]], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise SystemExit(f"Refusing to overwrite existing output (use --overwrite): {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(REQUIRED_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in REQUIRED_COLUMNS})


def _write_raw_snapshot_append_only(*, path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing raw snapshot (append-only): {path}")
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(serialized, encoding="utf-8")


def _deterministic_sample_close_cents(d: date, idx: int) -> int:
    """Deterministic synthetic ETH/USD close for sample-mode fixtures.

    This intentionally avoids network dependence and randomness so the committed
    sample stays stable across environments.
    """

    base_cents = 287_500 + (idx * 410)
    wave_cents = ((idx * 197) % 1_600) - 800
    dencun_bonus_cents = 6_000 if d >= date(2024, 3, 13) else 0
    april_recenter_cents = -3_000 if d >= date(2024, 4, 1) else 0
    close_cents = base_cents + wave_cents + dencun_bonus_cents + april_recenter_cents
    if close_cents <= 0:
        raise SystemExit(f"deterministic sample produced non-positive close at {d.isoformat()}")
    return close_cents


def _build_sample_rows() -> list[dict[str, str]]:
    dates = _iter_dates(SAMPLE_WINDOW_START, SAMPLE_WINDOW_END)
    rows: list[dict[str, str]] = []
    for idx, d in enumerate(dates):
        close_cents = _deterministic_sample_close_cents(d, idx)
        rows.append(
            {
                "date_utc": d.isoformat(),
                "eth_usd_close": f"{close_cents / 100:.2f}",
            }
        )

    # Hard assertion so sample mode remains locked to the canonical repo window.
    if rows[0]["date_utc"] != SAMPLE_WINDOW_START.isoformat() or rows[-1]["date_utc"] != SAMPLE_WINDOW_END.isoformat():
        raise SystemExit("sample mode window drift detected")
    return rows


def _fetch_json(url: str, *, timeout_seconds: int, coingecko_api_key: str | None) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "l2-l1-rent-analysis/prices_fetch.py",
    }
    if coingecko_api_key:
        # CoinGecko accepts this header for Demo keys; Pro keys may use x-cg-pro-api-key.
        headers["x-cg-demo-api-key"] = coingecko_api_key
        headers["x-cg-pro-api-key"] = coingecko_api_key

    req = Request(
        url,
        headers=headers,
        method="GET",
    )
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:  # nosec B310
            payload = resp.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise SystemExit(
                "CoinGecko authorization failed (HTTP "
                f"{exc.code}). Provide --coingecko-api-key or set COINGECKO_API_KEY."
            ) from exc
        raise SystemExit(f"CoinGecko request failed with HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise SystemExit(f"CoinGecko request failed: {exc.reason}") from exc
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit("CoinGecko response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise SystemExit("CoinGecko response had unexpected top-level shape")
    return parsed


def _coingecko_url(*, coin_id: str, vs_currency: str) -> str:
    query = urlencode({"vs_currency": vs_currency, "days": "max", "interval": "daily"})
    return f"{COINGECKO_MARKET_CHART_BASE.format(coin_id=coin_id)}?{query}"


def _normalize_coingecko_prices(
    *,
    payload: dict[str, Any],
    start_date: date,
    end_date: date,
) -> list[dict[str, str]]:
    prices = payload.get("prices")
    if not isinstance(prices, list):
        raise SystemExit("CoinGecko payload missing `prices` list")

    by_date: dict[str, float] = {}
    for item in prices:
        if not isinstance(item, list) or len(item) < 2:
            continue
        ts_raw = item[0]
        px_raw = item[1]

        if not isinstance(ts_raw, (int, float)) or not isinstance(px_raw, (int, float)):
            continue
        if not math.isfinite(float(px_raw)):
            continue

        dt = datetime.fromtimestamp(float(ts_raw) / 1000.0, tz=timezone.utc)
        d = dt.date()
        if d < start_date or d > end_date:
            continue
        by_date[d.isoformat()] = float(px_raw)

    rows: list[dict[str, str]] = []
    for d in sorted(by_date.keys()):
        rows.append(
            {
                "date_utc": d,
                "eth_usd_close": f"{by_date[d]:.6f}",
            }
        )
    return rows


def _summary(*, mode: str, out: Path, rows: list[dict[str, str]], raw_snapshot: Path | None) -> dict[str, object]:
    return {
        "mode": mode,
        "required_columns": list(REQUIRED_COLUMNS),
        "rows": len(rows),
        "first_date": rows[0]["date_utc"] if rows else None,
        "last_date": rows[-1]["date_utc"] if rows else None,
        "out": str(out.resolve()),
        "raw_snapshot": str(raw_snapshot.resolve()) if raw_snapshot else None,
    }


def _default_sample_out() -> Path:
    return REPO_ROOT / "data" / "samples" / "prices" / "prices_daily_sample.csv"


def _default_processed_out() -> Path:
    # CSV is used for stdlib-only portability.
    return REPO_ROOT / "data" / "processed" / "prices" / "prices_daily.csv"


def _default_raw_out(run_date: date) -> Path:
    return REPO_ROOT / "data" / "raw" / "prices" / run_date.isoformat() / "coingecko_eth_usd_market_chart.json"


def run_sample(*, out_path: Path, overwrite: bool) -> int:
    rows = _build_sample_rows()
    _assert_required_rows(rows)
    _write_csv_rows(path=out_path, rows=rows, overwrite=overwrite)

    print(json.dumps(_summary(mode="sample", out=out_path, rows=rows, raw_snapshot=None), indent=2, sort_keys=True))
    return 0


def run_snapshot(
    *,
    run_date: date | None,
    from_snapshot: Path | None,
    write_raw: bool,
    raw_out: Path | None,
    out_path: Path,
    overwrite: bool,
    start_date: date,
    end_date: date,
    coin_id: str,
    vs_currency: str,
    timeout_seconds: int,
    coingecko_api_key: str | None,
) -> int:
    if end_date < start_date:
        raise SystemExit(f"--end-date must be >= --start-date (start={start_date}, end={end_date})")

    if write_raw and from_snapshot is not None:
        raise SystemExit("--write-raw cannot be used with --from-snapshot")

    if from_snapshot is not None:
        try:
            payload_any = json.loads(from_snapshot.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SystemExit(f"snapshot file not found: {from_snapshot}") from exc
        except json.JSONDecodeError as exc:
            raise SystemExit(f"snapshot file is not valid JSON: {from_snapshot}") from exc

        if not isinstance(payload_any, dict):
            raise SystemExit("snapshot file must contain a JSON object")
        payload = payload_any
        raw_written = None
    else:
        if run_date is None:
            raise SystemExit("--run-date is required when fetching network snapshot")

        payload = _fetch_json(
            _coingecko_url(coin_id=coin_id, vs_currency=vs_currency),
            timeout_seconds=timeout_seconds,
            coingecko_api_key=coingecko_api_key,
        )
        raw_written = None
        if write_raw:
            raw_path = raw_out if raw_out is not None else _default_raw_out(run_date)
            _write_raw_snapshot_append_only(path=raw_path, payload=payload)
            raw_written = raw_path

    rows = _normalize_coingecko_prices(payload=payload, start_date=start_date, end_date=end_date)
    _assert_required_rows(rows)
    _write_csv_rows(path=out_path, rows=rows, overwrite=overwrite)

    print(json.dumps(_summary(mode="snapshot", out=out_path, rows=rows, raw_snapshot=raw_written), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="prices_fetch.py",
        description=(
            "ETH/USD prices ETL (stdlib-only). Generates deterministic sample output "
            "or normalizes CoinGecko daily closes into required columns."
        ),
        epilog=(
            "Examples:\n"
            "  python src/etl/prices_fetch.py --sample --overwrite\n"
            "  python src/etl/prices_fetch.py --run-date 2026-02-06 --write-raw --overwrite\n"
            "  python src/etl/prices_fetch.py --run-date 2026-02-06 --coingecko-api-key $COINGECKO_API_KEY --out data/processed/prices/prices_daily.csv --overwrite\n"
            "  python src/etl/prices_fetch.py --from-snapshot data/raw/prices/2026-02-06/coingecko_eth_usd_market_chart.json --out data/processed/prices/prices_daily.csv --overwrite"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    p.add_argument("--sample", action="store_true", help="Generate deterministic canonical sample window output")
    p.add_argument("--run-date", default=None, help="UTC run date (YYYY-MM-DD), required for network snapshot fetch mode")
    p.add_argument("--from-snapshot", default=None, help="Path to existing raw CoinGecko JSON snapshot (skip network)")
    p.add_argument("--write-raw", action="store_true", help="Write fetched raw snapshot JSON (append-only; refuses overwrite)")
    p.add_argument("--raw-out", default=None, help="Optional raw snapshot JSON path override")
    p.add_argument("--out", default=None, help="Output CSV path (defaults by mode)")
    p.add_argument("--start-date", default=PROTOCOL_START_DATE.isoformat(), help="Series start date UTC inclusive (default: 2022-01-01)")
    p.add_argument("--end-date", default=None, help="Series end date UTC inclusive (default: run-date for fetch mode, today for snapshot file mode)")
    p.add_argument("--coin-id", default="ethereum", help="CoinGecko coin id for snapshot mode (default: ethereum)")
    p.add_argument("--vs-currency", default="usd", help="Quote currency for snapshot mode (default: usd)")
    p.add_argument(
        "--coingecko-api-key",
        default=None,
        help="Optional CoinGecko API key (or set COINGECKO_API_KEY env var)",
    )
    p.add_argument("--timeout-seconds", type=int, default=45, help="HTTP timeout seconds for network snapshot mode")
    p.add_argument("--overwrite", action="store_true", help="Allow overwriting output CSV")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    if args.sample:
        if args.from_snapshot is not None:
            raise SystemExit("--sample cannot be combined with --from-snapshot")
        if args.write_raw:
            raise SystemExit("--sample cannot be combined with --write-raw")
        out = Path(args.out) if args.out else _default_sample_out()
        out_abs = out if out.is_absolute() else (REPO_ROOT / out)
        return run_sample(out_path=out_abs, overwrite=bool(args.overwrite))

    run_date = _parse_date(args.run_date, label="run-date") if args.run_date else None
    from_snapshot = Path(args.from_snapshot) if args.from_snapshot else None
    raw_out = Path(args.raw_out) if args.raw_out else None
    out = Path(args.out) if args.out else _default_processed_out()
    coingecko_api_key = (str(args.coingecko_api_key).strip() if args.coingecko_api_key else "") or os.getenv("COINGECKO_API_KEY")

    out_abs = out if out.is_absolute() else (REPO_ROOT / out)
    from_snapshot_abs = None if from_snapshot is None else (from_snapshot if from_snapshot.is_absolute() else (REPO_ROOT / from_snapshot))
    raw_out_abs = None if raw_out is None else (raw_out if raw_out.is_absolute() else (REPO_ROOT / raw_out))

    start_date = _parse_date(str(args.start_date), label="start-date")
    if args.end_date:
        end_date = _parse_date(str(args.end_date), label="end-date")
    elif run_date is not None:
        end_date = run_date
    else:
        end_date = datetime.now(timezone.utc).date()

    return run_snapshot(
        run_date=run_date,
        from_snapshot=from_snapshot_abs,
        write_raw=bool(args.write_raw),
        raw_out=raw_out_abs,
        out_path=out_abs,
        overwrite=bool(args.overwrite),
        start_date=start_date,
        end_date=end_date,
        coin_id=str(args.coin_id),
        vs_currency=str(args.vs_currency),
        timeout_seconds=int(args.timeout_seconds),
        coingecko_api_key=coingecko_api_key,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
