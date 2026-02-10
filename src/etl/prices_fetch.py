from __future__ import annotations

"""Prices ETL (stdlib-only).

Modes:
- `--sample`: generate deterministic ETH/USD daily closes for the canonical sample
  window (2024-02-20..2024-04-30).
- snapshot mode (default when `--sample` is not used): fetch a source API
  (CoinGecko primary, CryptoCompare fallback) or load a saved raw snapshot, normalize
  to daily closes, and write CSV.

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
CRYPTOCOMPARE_HISTODAY_BASE = "https://min-api.cryptocompare.com/data/v2/histoday"
YAHOO_CHART_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


class FetchError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


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


def _assert_window_coverage(*, rows: list[dict[str, str]], start_date: date, end_date: date) -> None:
    expected_dates = [d.isoformat() for d in _iter_dates(start_date, end_date)]
    seen_dates = {row["date_utc"] for row in rows}
    missing = [d for d in expected_dates if d not in seen_dates]
    if missing:
        preview = ", ".join(missing[:10])
        suffix = "" if len(missing) <= 10 else f", ... (+{len(missing) - 10} more)"
        raise SystemExit(
            f"Normalized daily series is missing {len(missing)} day(s) in {start_date.isoformat()}..{end_date.isoformat()}: "
            f"{preview}{suffix}"
        )


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


def _http_get_json(*, url: str, timeout_seconds: int, headers: dict[str, str], source_label: str) -> dict[str, Any]:
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:  # nosec B310
            payload = resp.read().decode("utf-8")
    except HTTPError as exc:
        raise FetchError(f"{source_label} request failed with HTTP {exc.code}: {exc.reason}", http_status=int(exc.code)) from exc
    except URLError as exc:
        raise FetchError(f"{source_label} request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise FetchError(f"{source_label} response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise FetchError(f"{source_label} response had unexpected top-level shape")
    return parsed


def _fetch_coingecko_json(*, url: str, timeout_seconds: int, coingecko_api_key: str | None) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "l2-l1-rent-analysis/prices_fetch.py",
    }
    if coingecko_api_key:
        # CoinGecko accepts this header for Demo keys; Pro keys may use x-cg-pro-api-key.
        headers["x-cg-demo-api-key"] = coingecko_api_key
        headers["x-cg-pro-api-key"] = coingecko_api_key

    try:
        return _http_get_json(url=url, timeout_seconds=timeout_seconds, headers=headers, source_label="CoinGecko")
    except FetchError as exc:
        if exc.http_status in {401, 403}:
            raise FetchError(
                "CoinGecko authorization failed (HTTP "
                f"{exc.http_status}). Provide --coingecko-api-key or set COINGECKO_API_KEY.",
                http_status=exc.http_status,
            ) from exc
        raise


def _fetch_yahoo_json(*, url: str, timeout_seconds: int) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "l2-l1-rent-analysis/prices_fetch.py",
    }
    return _http_get_json(url=url, timeout_seconds=timeout_seconds, headers=headers, source_label="Yahoo Finance")


def _coingecko_url(*, coin_id: str, vs_currency: str) -> str:
    query = urlencode({"vs_currency": vs_currency, "days": "max", "interval": "daily"})
    return f"{COINGECKO_MARKET_CHART_BASE.format(coin_id=coin_id)}?{query}"


def _cryptocompare_url(*, fsym: str, tsym: str, to_ts: int) -> str:
    query = urlencode(
        {
            "fsym": fsym,
            "tsym": tsym,
            "limit": "2000",
            "toTs": str(to_ts),
        }
    )
    return f"{CRYPTOCOMPARE_HISTODAY_BASE}?{query}"


def _yahoo_url(*, symbol: str, start_date: date, end_date: date) -> str:
    start_ts = int(datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc).timestamp())
    end_exclusive_ts = int(
        (datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc) + timedelta(days=1)).timestamp()
    )
    query = urlencode(
        {
            "period1": str(start_ts),
            "period2": str(end_exclusive_ts),
            "interval": "1d",
            "events": "history",
            "includePrePost": "false",
        }
    )
    return f"{YAHOO_CHART_BASE.format(symbol=symbol)}?{query}"


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


def _normalize_yahoo_prices(
    *,
    payload: dict[str, Any],
    start_date: date,
    end_date: date,
) -> list[dict[str, str]]:
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise SystemExit("Yahoo payload missing `chart` object")

    chart_error = chart.get("error")
    if chart_error is not None:
        raise SystemExit(f"Yahoo payload reported error: {chart_error!r}")

    result_list = chart.get("result")
    if not isinstance(result_list, list) or not result_list or not isinstance(result_list[0], dict):
        raise SystemExit("Yahoo payload missing `chart.result[0]` object")
    result = result_list[0]

    ts_list = result.get("timestamp")
    if not isinstance(ts_list, list):
        raise SystemExit("Yahoo payload missing `timestamp` list")

    indicators = result.get("indicators")
    if not isinstance(indicators, dict):
        raise SystemExit("Yahoo payload missing `indicators` object")
    quotes = indicators.get("quote")
    if not isinstance(quotes, list) or not quotes or not isinstance(quotes[0], dict):
        raise SystemExit("Yahoo payload missing `indicators.quote[0]` object")
    closes = quotes[0].get("close")
    if not isinstance(closes, list):
        raise SystemExit("Yahoo payload missing `indicators.quote[0].close` list")

    by_date: dict[str, float] = {}
    for i, ts_raw in enumerate(ts_list):
        if not isinstance(ts_raw, (int, float)):
            continue
        if i >= len(closes):
            continue
        px_raw = closes[i]
        if not isinstance(px_raw, (int, float)):
            continue
        if not math.isfinite(float(px_raw)):
            continue

        dt = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
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


def _normalize_cryptocompare_prices(
    *,
    payload: dict[str, Any],
    start_date: date,
    end_date: date,
) -> list[dict[str, str]]:
    response_code = payload.get("Response")
    if response_code != "Success":
        raise SystemExit(f"CryptoCompare payload reported non-success response: {response_code!r}")

    data_obj = payload.get("Data")
    if not isinstance(data_obj, dict):
        raise SystemExit("CryptoCompare payload missing `Data` object")
    items = data_obj.get("Data")
    if not isinstance(items, list):
        raise SystemExit("CryptoCompare payload missing `Data.Data` list")

    by_date: dict[str, float] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        ts_raw = item.get("time")
        px_raw = item.get("close")
        if not isinstance(ts_raw, (int, float)):
            continue
        if not isinstance(px_raw, (int, float)):
            continue
        if not math.isfinite(float(px_raw)):
            continue

        dt = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
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


def _normalize_prices(
    *,
    source: str,
    payload: dict[str, Any],
    start_date: date,
    end_date: date,
) -> list[dict[str, str]]:
    if source == "coingecko":
        return _normalize_coingecko_prices(payload=payload, start_date=start_date, end_date=end_date)
    if source == "cryptocompare":
        return _normalize_cryptocompare_prices(payload=payload, start_date=start_date, end_date=end_date)
    if source == "yahoo":
        return _normalize_yahoo_prices(payload=payload, start_date=start_date, end_date=end_date)
    raise SystemExit(f"Unsupported source for normalization: {source!r}")


def _summary(*, mode: str, source: str, out: Path, rows: list[dict[str, str]], raw_snapshot: Path | None) -> dict[str, object]:
    return {
        "mode": mode,
        "source": source,
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


def _default_raw_out(run_date: date, *, source: str) -> Path:
    if source == "coingecko":
        filename = "coingecko_eth_usd_market_chart.json"
    elif source == "cryptocompare":
        filename = "cryptocompare_eth_usd_histoday.json"
    elif source == "yahoo":
        filename = "yahoo_eth_usd_chart.json"
    else:
        raise SystemExit(f"Unsupported source for raw snapshot path: {source!r}")
    return REPO_ROOT / "data" / "raw" / "prices" / run_date.isoformat() / filename


def _source_request_url(
    *,
    source: str,
    start_date: date,
    end_date: date,
    coin_id: str,
    vs_currency: str,
    cryptocompare_fsym: str,
    cryptocompare_tsym: str,
    yahoo_symbol: str,
) -> str:
    if source == "coingecko":
        return _coingecko_url(coin_id=coin_id, vs_currency=vs_currency)
    if source == "cryptocompare":
        to_ts = int(datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc).timestamp())
        return _cryptocompare_url(fsym=cryptocompare_fsym, tsym=cryptocompare_tsym, to_ts=to_ts)
    if source == "yahoo":
        return _yahoo_url(symbol=yahoo_symbol, start_date=start_date, end_date=end_date)
    raise SystemExit(f"Unsupported source: {source!r}")


def _fetch_source_json(
    *,
    source: str,
    request_url: str,
    timeout_seconds: int,
    coingecko_api_key: str | None,
) -> dict[str, Any]:
    if source == "coingecko":
        return _fetch_coingecko_json(
            url=request_url,
            timeout_seconds=timeout_seconds,
            coingecko_api_key=coingecko_api_key,
        )
    if source == "cryptocompare":
        payload = _http_get_json(
            url=request_url,
            timeout_seconds=timeout_seconds,
            headers={"Accept": "application/json", "User-Agent": "l2-l1-rent-analysis/prices_fetch.py"},
            source_label="CryptoCompare",
        )
        if payload.get("Response") != "Success":
            message = payload.get("Message")
            raise FetchError(
                f"CryptoCompare response was not successful: {message!r}",
            )
        return payload
    if source == "yahoo":
        return _fetch_yahoo_json(url=request_url, timeout_seconds=timeout_seconds)
    raise SystemExit(f"Unsupported source: {source!r}")


def _snapshot_record(*, source: str, request_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": source,
        "request_url": request_url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def _extract_snapshot_source_payload(*, snapshot_obj: dict[str, Any], default_source: str) -> tuple[str, dict[str, Any]]:
    maybe_source = snapshot_obj.get("source")
    maybe_payload = snapshot_obj.get("payload")
    if isinstance(maybe_source, str) and isinstance(maybe_payload, dict):
        return maybe_source, maybe_payload
    return default_source, snapshot_obj


def run_sample(*, out_path: Path, overwrite: bool) -> int:
    rows = _build_sample_rows()
    _assert_required_rows(rows)
    _write_csv_rows(path=out_path, rows=rows, overwrite=overwrite)

    print(
        json.dumps(
            _summary(mode="sample", source="deterministic_sample", out=out_path, rows=rows, raw_snapshot=None),
            indent=2,
            sort_keys=True,
        )
    )
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
    source: str,
    coin_id: str,
    vs_currency: str,
    cryptocompare_fsym: str,
    cryptocompare_tsym: str,
    yahoo_symbol: str,
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
        source_used, payload = _extract_snapshot_source_payload(snapshot_obj=payload_any, default_source=source)
        raw_written = None
    else:
        if run_date is None:
            raise SystemExit("--run-date is required when fetching network snapshot")

        source_used = source
        request_url = _source_request_url(
            source=source_used,
            start_date=start_date,
            end_date=end_date,
            coin_id=coin_id,
            vs_currency=vs_currency,
            cryptocompare_fsym=cryptocompare_fsym,
            cryptocompare_tsym=cryptocompare_tsym,
            yahoo_symbol=yahoo_symbol,
        )
        try:
            payload = _fetch_source_json(
                source=source_used,
                request_url=request_url,
                timeout_seconds=timeout_seconds,
                coingecko_api_key=coingecko_api_key,
            )
        except FetchError as exc:
            if source == "coingecko" and coingecko_api_key is None and exc.http_status in {401, 403}:
                source_used = "cryptocompare"
                request_url = _source_request_url(
                    source=source_used,
                    start_date=start_date,
                    end_date=end_date,
                    coin_id=coin_id,
                    vs_currency=vs_currency,
                    cryptocompare_fsym=cryptocompare_fsym,
                    cryptocompare_tsym=cryptocompare_tsym,
                    yahoo_symbol=yahoo_symbol,
                )
                print(
                    "CoinGecko returned authorization failure without API key; retrying with CryptoCompare.",
                    file=sys.stderr,
                )
                payload = _fetch_source_json(
                    source=source_used,
                    request_url=request_url,
                    timeout_seconds=timeout_seconds,
                    coingecko_api_key=coingecko_api_key,
                )
            else:
                raise SystemExit(str(exc)) from exc
        raw_written = None
        if write_raw:
            raw_path = raw_out if raw_out is not None else _default_raw_out(run_date, source=source_used)
            _write_raw_snapshot_append_only(
                path=raw_path,
                payload=_snapshot_record(source=source_used, request_url=request_url, payload=payload),
            )
            raw_written = raw_path

    rows = _normalize_prices(source=source_used, payload=payload, start_date=start_date, end_date=end_date)
    _assert_required_rows(rows)
    _assert_window_coverage(rows=rows, start_date=start_date, end_date=end_date)
    _write_csv_rows(path=out_path, rows=rows, overwrite=overwrite)

    print(
        json.dumps(
            _summary(mode="snapshot", source=source_used, out=out_path, rows=rows, raw_snapshot=raw_written),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="prices_fetch.py",
        description=(
            "ETH/USD prices ETL (stdlib-only). Generates deterministic sample output "
            "or normalizes CoinGecko/CryptoCompare/Yahoo daily closes into required columns."
        ),
        epilog=(
            "Examples:\n"
            "  python src/etl/prices_fetch.py --sample --overwrite\n"
            "  python src/etl/prices_fetch.py --run-date 2026-02-06 --write-raw --overwrite\n"
            "  python src/etl/prices_fetch.py --run-date 2026-02-06 --source cryptocompare --write-raw --overwrite\n"
            "  python src/etl/prices_fetch.py --run-date 2026-02-06 --source yahoo --write-raw --overwrite\n"
            "  python src/etl/prices_fetch.py --run-date 2026-02-06 --coingecko-api-key $COINGECKO_API_KEY --out data/processed/prices/prices_daily.csv --overwrite\n"
            "  python src/etl/prices_fetch.py --from-snapshot data/raw/prices/2026-02-06/coingecko_eth_usd_market_chart.json --out data/processed/prices/prices_daily.csv --overwrite"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    p.add_argument("--sample", action="store_true", help="Generate deterministic canonical sample window output")
    p.add_argument("--run-date", default=None, help="UTC run date (YYYY-MM-DD), required for network snapshot fetch mode")
    p.add_argument(
        "--from-snapshot",
        default=None,
        help="Path to existing raw snapshot JSON (skip network; supports legacy raw CoinGecko payload or source-wrapped snapshots)",
    )
    p.add_argument("--write-raw", action="store_true", help="Write fetched raw snapshot JSON (append-only; refuses overwrite)")
    p.add_argument("--raw-out", default=None, help="Optional raw snapshot JSON path override")
    p.add_argument("--out", default=None, help="Output CSV path (defaults by mode)")
    p.add_argument("--start-date", default=PROTOCOL_START_DATE.isoformat(), help="Series start date UTC inclusive (default: 2022-01-01)")
    p.add_argument("--end-date", default=None, help="Series end date UTC inclusive (default: run-date for fetch mode, today for snapshot file mode)")
    p.add_argument(
        "--source",
        choices=["coingecko", "cryptocompare", "yahoo"],
        default="coingecko",
        help="Snapshot source (default: coingecko; auto-falls back to cryptocompare on coingecko auth failure without API key)",
    )
    p.add_argument("--coin-id", default="ethereum", help="CoinGecko coin id for snapshot mode (default: ethereum)")
    p.add_argument("--vs-currency", default="usd", help="Quote currency for snapshot mode (default: usd)")
    p.add_argument("--cryptocompare-fsym", default="ETH", help="CryptoCompare base symbol (default: ETH)")
    p.add_argument("--cryptocompare-tsym", default="USD", help="CryptoCompare quote symbol (default: USD)")
    p.add_argument("--yahoo-symbol", default="ETH-USD", help="Yahoo Finance symbol for snapshot mode (default: ETH-USD)")
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
        source=str(args.source),
        coin_id=str(args.coin_id),
        vs_currency=str(args.vs_currency),
        cryptocompare_fsym=str(args.cryptocompare_fsym),
        cryptocompare_tsym=str(args.cryptocompare_tsym),
        yahoo_symbol=str(args.yahoo_symbol),
        timeout_seconds=int(args.timeout_seconds),
        coingecko_api_key=coingecko_api_key,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
