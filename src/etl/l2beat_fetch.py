from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.etl.offchain.files import ensure_dir, write_text_append_only  # noqa: E402
from src.etl.offchain.http import http_get_text  # noqa: E402
from src.etl.offchain.trpc import trpc_query_batch1  # noqa: E402


L2BEAT_COSTS_PAGE_URL = "https://l2beat.com/scaling/costs"
L2BEAT_TRPC_BASE_URL = "https://l2beat.com/api/trpc"

TABLE_PROCEDURE = "costs.table"
CHART_PROCEDURE = "costs.chart"
PROJECT_CHART_PROCEDURE = "costs.projectChart"

REQUIRED_COLUMNS = ("date_utc", "rollup_id", "l2beat_slug", "total_cost_eth", "total_cost_usd")
ETH_COMPONENT_INDEXES = (2, 5, 8, 11)
USD_COMPONENT_INDEXES = (3, 6, 9, 12)

SAMPLE_WINDOW_START = date(2024, 2, 20)
SAMPLE_WINDOW_END = date(2024, 4, 30)
SAMPLE_ROLLUPS = ("arbitrum", "optimism", "base")


@dataclass(frozen=True)
class RegistryRow:
    rollup_id: str
    l2beat_slug: str
    in_scope: bool
    status: str
    start_date_utc: date | None
    end_date_utc: date | None

    def includes(self, d: date) -> bool:
        if self.status == "deprecated":
            return False
        if not self.in_scope:
            return False
        if self.start_date_utc is not None and d < self.start_date_utc:
            return False
        if self.end_date_utc is not None and d > self.end_date_utc:
            return False
        if self.status == "inactive" and self.end_date_utc is None:
            raise SystemExit(
                f"registry row {self.rollup_id!r} has status=inactive but missing end_date_utc"
            )
        return True

    def overlaps(self, start: date, end: date) -> bool:
        if self.status == "deprecated" or not self.in_scope:
            return False
        if self.end_date_utc is not None and self.end_date_utc < start:
            return False
        if self.start_date_utc is not None and self.start_date_utc > end:
            return False
        return True


@dataclass(frozen=True)
class SnapshotResult:
    snapshot_dir: Path
    table_path: Path
    requested_slugs: list[str]
    available_slugs: list[str]
    missing_from_table_slugs: list[str]
    written_files: list[Path]
    reused_files: list[Path]


@dataclass(frozen=True)
class NormalizationResult:
    rows: list[dict[str, object]]
    counts: dict[str, int]


def _parse_date(value: str, *, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {label} date (expected YYYY-MM-DD): {value!r}") from exc


def _parse_optional_date(value: str) -> date | None:
    s = (value or "").strip()
    if s == "":
        return None
    return _parse_date(s, label="registry")


def _parse_bool(value: str) -> bool:
    v = (value or "").strip().lower()
    if v in {"true", "1", "yes", "y"}:
        return True
    if v in {"false", "0", "no", "n", ""}:
        return False
    raise SystemExit(f"Invalid boolean value: {value!r}")


def _date_to_unix_seconds(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def _render_command_tokens_for_manifest(root: Path) -> list[str]:
    argv0 = Path(sys.argv[0])
    try:
        script_token = str(argv0.resolve().relative_to(root.resolve()))
    except Exception:
        script_token = sys.argv[0]
    return ["python", script_token, *sys.argv[1:]]


def _write_raw_manifest(*, source: str, snapshot_dir: Path, as_of: date) -> Path:
    root = REPO_ROOT
    helper = root / "scripts" / "make_raw_manifest.py"
    if not helper.exists():
        raise SystemExit(f"missing helper script (expected): {helper}")

    cmd = [
        sys.executable,
        str(helper),
        source,
        str(snapshot_dir),
        "--as-of",
        as_of.isoformat(),
        "--",
        *_render_command_tokens_for_manifest(root),
    ]
    subprocess.run(cmd, cwd=root, check=True)
    return root / "data" / "raw_manifest" / f"{source}_{as_of.isoformat()}.json"


def _write_processed_manifest(
    *,
    name: str,
    as_of: date,
    inputs: list[Path],
    outputs: list[Path],
    meta: dict[str, object],
    out_path: Path | None = None,
) -> Path:
    root = REPO_ROOT
    helper = root / "scripts" / "make_processed_manifest.py"
    if not helper.exists():
        raise SystemExit(f"missing helper script (expected): {helper}")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tf:
        json.dump(meta, tf, indent=2, sort_keys=True)
        tf.write("\n")
        meta_path = Path(tf.name)

    try:
        cmd: list[str] = [
            sys.executable,
            str(helper),
            name,
            "--as-of",
            as_of.isoformat(),
            "--inputs",
            *[str(p) for p in inputs],
            "--outputs",
            *[str(p) for p in outputs],
            "--meta-json",
            str(meta_path),
        ]
        if out_path is not None:
            cmd.extend(["--out", str(out_path)])
        cmd.extend(["--", *_render_command_tokens_for_manifest(root)])
        subprocess.run(cmd, cwd=root, check=True)
    finally:
        try:
            meta_path.unlink()
        except OSError:
            pass

    return (
        out_path
        if out_path is not None
        else (root / "data" / "processed_manifest" / f"{name}_{as_of.isoformat()}.json")
    )


def _parse_ssr_data_from_html(html: str) -> dict[str, Any]:
    m = re.search(r"window\.__SSR_DATA__\s*=\s*", html)
    if m is None:
        raise ValueError(
            "Could not find window.__SSR_DATA__ in L2BEAT HTML (site structure changed?)"
        )

    tail = html[m.end() :].lstrip()
    if not tail.startswith("{"):
        brace = tail.find("{")
        if brace == -1:
            raise ValueError("Could not find JSON object start for window.__SSR_DATA__")
        tail = tail[brace:]

    try:
        data, _end = json.JSONDecoder().raw_decode(tail)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Could not decode window.__SSR_DATA__ JSON (site structure changed?)"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("SSR data is not an object")
    return data


def _infer_default_range_seconds(ssr_data: dict[str, Any]) -> tuple[int, int]:
    """Best-effort: read the first dehydrated query key input range."""
    props = ssr_data.get("props")
    if not isinstance(props, dict):
        raise ValueError("SSR missing props")
    qs = props.get("queryState")
    if not isinstance(qs, dict):
        raise ValueError("SSR missing queryState")
    queries = qs.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("SSR queryState.queries missing/empty")
    q0 = queries[0]
    if not isinstance(q0, dict):
        raise ValueError("SSR queryState.queries[0] invalid")
    qk = q0.get("queryKey")
    if not isinstance(qk, list) or len(qk) < 2:
        raise ValueError("SSR queryKey missing/invalid")
    meta = qk[1]
    if not isinstance(meta, dict):
        raise ValueError("SSR queryKey[1] invalid")
    inp = meta.get("input")
    if not isinstance(inp, dict):
        raise ValueError("SSR queryKey[1].input missing/invalid")
    rng = inp.get("range")
    if not isinstance(rng, list) or len(rng) != 2:
        raise ValueError("SSR input.range missing/invalid")
    a, b = rng
    if not (isinstance(a, int) and isinstance(b, int)):
        raise ValueError("SSR input.range values are not ints")
    return a, b


def _parse_trpc_result_data(raw_response_text: str, *, label: str) -> Any:
    try:
        outer = json.loads(raw_response_text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {label}: {exc}") from exc
    if not isinstance(outer, list) or not outer:
        raise SystemExit(f"Unexpected tRPC response shape for {label}: expected non-empty list")
    item = outer[0]
    if not isinstance(item, dict):
        raise SystemExit(f"Unexpected tRPC response item for {label}: expected object")
    if "error" in item:
        raise SystemExit(f"tRPC error in {label}: {item['error']!r}")
    result = item.get("result")
    if not isinstance(result, dict):
        raise SystemExit(f"Unexpected tRPC response in {label}: missing result object")
    data = result.get("data")
    if not isinstance(data, str):
        raise SystemExit(f"Unexpected tRPC response in {label}: result.data is not a string")
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid inner JSON payload in {label}: {exc}") from exc


def _write_raw_snapshot(*, out_dir: Path, filename: str, text: str) -> Path:
    out_path = out_dir / filename
    write_text_append_only(out_path, text, encoding="utf-8")
    return out_path


def _safe_slug_for_filename(slug: str) -> str:
    if slug.strip() in {"", ".", ".."}:
        raise SystemExit(f"Invalid slug for file naming: {slug!r}")
    if "/" in slug or "\\" in slug:
        raise SystemExit(f"Invalid slug for file naming (path separators are not allowed): {slug!r}")
    return slug


def _coerce_optional_float(value: object, *, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise SystemExit(f"Invalid numeric value for {label}: bool is not allowed")
    if isinstance(value, (int, float)):
        out = float(value)
    elif isinstance(value, str):
        s = value.strip()
        if s == "":
            return None
        try:
            out = float(s)
        except ValueError as exc:
            raise SystemExit(f"Invalid numeric value for {label}: {value!r}") from exc
    else:
        raise SystemExit(f"Invalid numeric value for {label}: {value!r}")
    if not math.isfinite(out):
        raise SystemExit(f"Non-finite numeric value for {label}: {value!r}")
    return out


def load_registry(path: Path) -> dict[str, RegistryRow]:
    if not path.exists():
        raise SystemExit(f"registry not found: {path}")

    out: dict[str, RegistryRow] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit("registry CSV missing header row")
        required = {
            "rollup_id",
            "l2beat_slug",
            "in_scope",
            "status",
            "start_date_utc",
            "end_date_utc",
        }
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise SystemExit(f"registry CSV missing required columns: {missing}")

        for i, row in enumerate(reader, start=2):
            rollup_id = (row.get("rollup_id") or "").strip()
            if rollup_id == "":
                raise SystemExit(f"registry row {i}: missing rollup_id")
            slug = (row.get("l2beat_slug") or "").strip()
            in_scope = _parse_bool(row.get("in_scope", ""))
            status = (row.get("status") or "").strip().lower() or "active"
            start = _parse_optional_date(row.get("start_date_utc", ""))
            end = _parse_optional_date(row.get("end_date_utc", ""))

            if in_scope and slug == "":
                raise SystemExit(f"registry row {i}: in-scope rollup missing l2beat_slug ({rollup_id!r})")
            if slug == "":
                continue
            if slug in out and out[slug].rollup_id != rollup_id:
                raise SystemExit(
                    f"registry has ambiguous l2beat_slug mapping: {slug!r} -> "
                    f"{out[slug].rollup_id!r} and {rollup_id!r}"
                )
            out[slug] = RegistryRow(
                rollup_id=rollup_id,
                l2beat_slug=slug,
                in_scope=in_scope,
                status=status,
                start_date_utc=start,
                end_date_utc=end,
            )
    if not out:
        raise SystemExit(f"registry has no non-empty l2beat_slug rows: {path}")
    return out


def cmd_discover() -> int:
    html = http_get_text(L2BEAT_COSTS_PAGE_URL, timeout_seconds=30)
    ssr = _parse_ssr_data_from_html(html)
    default_start, default_end = _infer_default_range_seconds(ssr)
    print(
        json.dumps(
            {
                "costs_page_url": L2BEAT_COSTS_PAGE_URL,
                "trpc_base_url": L2BEAT_TRPC_BASE_URL,
                "procedures_observed": [TABLE_PROCEDURE, CHART_PROCEDURE, PROJECT_CHART_PROCEDURE],
                "default_range_seconds": [default_start, default_end],
                "notes": "Use tRPC batch=1 input encoding; see data/samples/l2beat/README.md.",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _resolve_query_range(range_start: int | None, range_end: int | None) -> tuple[int, int]:
    if range_start is not None and range_end is not None:
        start_ts, end_ts = int(range_start), int(range_end)
    else:
        html = http_get_text(L2BEAT_COSTS_PAGE_URL, timeout_seconds=30)
        ssr = _parse_ssr_data_from_html(html)
        start_ts, end_ts = _infer_default_range_seconds(ssr)
    if start_ts >= end_ts:
        raise SystemExit(f"Invalid query range: start_ts={start_ts} end_ts={end_ts}")
    return start_ts, end_ts


def cmd_snapshot(
    *,
    run_date: str,
    mode: str,
    filter_type: str | None,
    project_id: str | None,
    range_start: int | None,
    range_end: int | None,
) -> int:
    out_dir = REPO_ROOT / "data" / "raw" / "l2beat" / run_date
    ensure_dir(out_dir)
    start_ts, end_ts = _resolve_query_range(range_start=range_start, range_end=range_end)

    if mode == "table":
        if filter_type is None:
            raise SystemExit("--filter-type is required for mode=table")
        input_obj = {"range": [start_ts, end_ts], "filter": {"type": filter_type}}
        res = trpc_query_batch1(
            base_url=L2BEAT_TRPC_BASE_URL,
            procedure=TABLE_PROCEDURE,
            input_obj=input_obj,
        )
        _write_raw_snapshot(
            out_dir=out_dir,
            filename=f"costs_table_{filter_type}.json",
            text=res.raw_response_text,
        )
        return 0

    if mode == "chart":
        if filter_type is None:
            raise SystemExit("--filter-type is required for mode=chart")
        input_obj = {"range": [start_ts, end_ts], "filter": {"type": filter_type}}
        res = trpc_query_batch1(
            base_url=L2BEAT_TRPC_BASE_URL,
            procedure=CHART_PROCEDURE,
            input_obj=input_obj,
        )
        _write_raw_snapshot(
            out_dir=out_dir,
            filename=f"costs_chart_{filter_type}.json",
            text=res.raw_response_text,
        )
        return 0

    if mode == "projectChart":
        if project_id is None:
            raise SystemExit("--project-id is required for mode=projectChart")
        input_obj = {"range": [start_ts, end_ts], "projectId": project_id}
        res = trpc_query_batch1(
            base_url=L2BEAT_TRPC_BASE_URL,
            procedure=PROJECT_CHART_PROCEDURE,
            input_obj=input_obj,
        )
        slug = _safe_slug_for_filename(project_id)
        _write_raw_snapshot(
            out_dir=out_dir,
            filename=f"project_chart_{slug}.json",
            text=res.raw_response_text,
        )
        return 0

    raise SystemExit(f"Unknown mode: {mode}")


def _window_to_range_seconds(*, start_date: date, end_date: date) -> tuple[int, int]:
    if end_date < start_date:
        raise SystemExit(
            f"Invalid date window: end_date ({end_date.isoformat()}) < start_date ({start_date.isoformat()})"
        )
    start_ts = _date_to_unix_seconds(start_date)
    end_exclusive_ts = _date_to_unix_seconds(end_date + timedelta(days=1))
    if start_ts >= end_exclusive_ts:
        raise SystemExit("Invalid computed query range for L2BEAT")
    return start_ts, end_exclusive_ts


def _load_table_payload(path: Path) -> dict[str, Any]:
    payload = _parse_trpc_result_data(path.read_text(encoding="utf-8"), label=str(path))
    if not isinstance(payload, dict):
        raise SystemExit(f"Unexpected costs.table payload shape (expected object): {path}")
    return payload


def _snapshot_full(
    *,
    run_date: date,
    start_ts: int,
    end_ts: int,
    filter_type: str,
    requested_slugs: list[str],
) -> SnapshotResult:
    snapshot_dir = REPO_ROOT / "data" / "raw" / "l2beat" / run_date.isoformat()
    ensure_dir(snapshot_dir)

    written_files: list[Path] = []
    reused_files: list[Path] = []

    table_path = snapshot_dir / f"costs_table_{filter_type}.json"
    table_payload: dict[str, Any]
    if table_path.exists():
        table_payload = _load_table_payload(table_path)
        reused_files.append(table_path)
    else:
        table_input = {"range": [start_ts, end_ts], "filter": {"type": filter_type}}
        table_res = trpc_query_batch1(
            base_url=L2BEAT_TRPC_BASE_URL,
            procedure=TABLE_PROCEDURE,
            input_obj=table_input,
            timeout_seconds=60,
        )
        _write_raw_snapshot(
            out_dir=snapshot_dir,
            filename=table_path.name,
            text=table_res.raw_response_text,
        )
        table_payload = _parse_trpc_result_data(table_res.raw_response_text, label=table_path.name)
        if not isinstance(table_payload, dict):
            raise SystemExit("Unexpected costs.table payload shape (expected object)")
        written_files.append(table_path)

    available_slugs = sorted([str(k) for k in table_payload.keys()])
    requested = sorted({s for s in requested_slugs})
    missing = sorted([s for s in requested if s not in table_payload])
    to_fetch = [s for s in requested if s in table_payload]

    for slug in to_fetch:
        safe_slug = _safe_slug_for_filename(slug)
        out_name = f"project_chart_{safe_slug}.json"
        out_path = snapshot_dir / out_name
        if out_path.exists():
            reused_files.append(out_path)
            continue
        input_obj = {"range": [start_ts, end_ts], "projectId": slug}
        res = trpc_query_batch1(
            base_url=L2BEAT_TRPC_BASE_URL,
            procedure=PROJECT_CHART_PROCEDURE,
            input_obj=input_obj,
            timeout_seconds=60,
        )
        _write_raw_snapshot(out_dir=snapshot_dir, filename=out_name, text=res.raw_response_text)
        written_files.append(out_path)

    return SnapshotResult(
        snapshot_dir=snapshot_dir,
        table_path=table_path,
        requested_slugs=requested,
        available_slugs=available_slugs,
        missing_from_table_slugs=missing,
        written_files=written_files,
        reused_files=reused_files,
    )


def _parse_project_chart_rows(*, payload: Any, slug: str) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise SystemExit(f"Unexpected projectChart payload for {slug!r}: expected object")
    chart = payload.get("chart")
    if not isinstance(chart, list):
        raise SystemExit(f"Unexpected projectChart payload for {slug!r}: missing chart list")

    rows: list[dict[str, object]] = []
    sum_eth = 0.0
    sum_usd = 0.0
    for i, point in enumerate(chart):
        if not isinstance(point, list):
            raise SystemExit(f"Unexpected chart row type for {slug!r} at index {i}: expected list")
        min_len = max(max(ETH_COMPONENT_INDEXES), max(USD_COMPONENT_INDEXES)) + 1
        if len(point) < min_len:
            raise SystemExit(
                f"Unexpected chart row length for {slug!r} at index {i}: "
                f"expected at least {min_len}, got {len(point)}"
            )

        ts_raw = point[0]
        if isinstance(ts_raw, bool) or not isinstance(ts_raw, (int, float)):
            raise SystemExit(
                f"Unexpected timestamp value in projectChart for {slug!r} at index {i}: {ts_raw!r}"
            )
        ts = int(ts_raw)
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()

        eth_total = 0.0
        usd_total = 0.0
        for idx in ETH_COMPONENT_INDEXES:
            comp = _coerce_optional_float(point[idx], label=f"{slug}[{i}].eth_component[{idx}]")
            if comp is not None:
                if comp < 0:
                    raise SystemExit(f"Negative ETH component in projectChart for {slug!r} at index {i}")
                eth_total += comp
        for idx in USD_COMPONENT_INDEXES:
            comp = _coerce_optional_float(point[idx], label=f"{slug}[{i}].usd_component[{idx}]")
            if comp is not None:
                if comp < 0:
                    raise SystemExit(f"Negative USD component in projectChart for {slug!r} at index {i}")
                usd_total += comp

        rows.append(
            {
                "date_utc": d,
                "l2beat_slug": slug,
                "total_cost_eth": eth_total,
                "total_cost_usd": usd_total,
            }
        )
        sum_eth += eth_total
        sum_usd += usd_total

    stats = payload.get("stats")
    if isinstance(stats, dict):
        total = stats.get("total")
        if isinstance(total, dict):
            expected_eth = _coerce_optional_float(total.get("eth"), label=f"{slug}.stats.total.eth")
            expected_usd = _coerce_optional_float(total.get("usd"), label=f"{slug}.stats.total.usd")
            if expected_eth is not None:
                tol = max(1e-9, abs(expected_eth) * 1e-9)
                if abs(sum_eth - expected_eth) > tol:
                    raise SystemExit(
                        f"ETH total mismatch for {slug!r}: rows sum={sum_eth}, stats.total.eth={expected_eth}"
                    )
            if expected_usd is not None:
                tol = max(1e-6, abs(expected_usd) * 1e-9)
                if abs(sum_usd - expected_usd) > tol:
                    raise SystemExit(
                        f"USD total mismatch for {slug!r}: rows sum={sum_usd}, stats.total.usd={expected_usd}"
                    )
    return rows


def _normalize_from_snapshot(
    *,
    snapshot_dir: Path,
    registry_by_slug: dict[str, RegistryRow],
    start_date: date,
    end_date: date,
) -> NormalizationResult:
    if not snapshot_dir.exists():
        raise SystemExit(f"snapshot dir does not exist: {snapshot_dir}")
    if not snapshot_dir.is_dir():
        raise SystemExit(f"snapshot path is not a directory: {snapshot_dir}")

    chart_files = sorted(snapshot_dir.glob("project_chart_*.json"))
    if not chart_files:
        raise SystemExit(
            f"No project_chart_*.json files found in snapshot dir: {snapshot_dir}. "
            "Run with --run-date to fetch snapshots first."
        )

    counts: dict[str, int] = {
        "chart_files_total": len(chart_files),
        "chart_files_skipped_unknown_slug": 0,
        "rows_total_chart_points": 0,
        "rows_filtered_outside_window": 0,
        "rows_filtered_by_registry_window": 0,
        "rows_emitted": 0,
    }

    rows_out: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    for path in chart_files:
        slug = path.stem.removeprefix("project_chart_")
        row_meta = registry_by_slug.get(slug)
        if row_meta is None:
            counts["chart_files_skipped_unknown_slug"] += 1
            continue
        if not row_meta.in_scope or row_meta.status == "deprecated":
            counts["chart_files_skipped_unknown_slug"] += 1
            continue

        payload = _parse_trpc_result_data(path.read_text(encoding="utf-8"), label=str(path))
        points = _parse_project_chart_rows(payload=payload, slug=slug)
        counts["rows_total_chart_points"] += len(points)
        for point in points:
            d = _parse_date(str(point["date_utc"]), label="date_utc")
            if d < start_date or d > end_date:
                counts["rows_filtered_outside_window"] += 1
                continue
            if not row_meta.includes(d):
                counts["rows_filtered_by_registry_window"] += 1
                continue

            key = (d.isoformat(), row_meta.rollup_id)
            if key in seen:
                raise SystemExit(
                    f"Duplicate normalized row for date={key[0]} rollup_id={key[1]} (slug={slug})"
                )
            seen.add(key)
            rows_out.append(
                {
                    "date_utc": d.isoformat(),
                    "rollup_id": row_meta.rollup_id,
                    "l2beat_slug": slug,
                    "total_cost_eth": float(point["total_cost_eth"]),
                    "total_cost_usd": float(point["total_cost_usd"]),
                }
            )

    rows_out.sort(key=lambda r: (str(r["date_utc"]), str(r["rollup_id"])))
    counts["rows_emitted"] = len(rows_out)
    return NormalizationResult(rows=rows_out, counts=counts)


def _assert_required_schema(rows: list[dict[str, object]]) -> None:
    if not rows:
        raise SystemExit("Normalized daily table is empty; refusing to write output")

    required = set(REQUIRED_COLUMNS)
    for i, row in enumerate(rows):
        missing = sorted(required - set(row.keys()))
        if missing:
            raise SystemExit(f"row {i}: missing required columns: {missing}")
        _parse_date(str(row.get("date_utc", "")), label="date_utc")

        for col in ["rollup_id", "l2beat_slug"]:
            v = row.get(col)
            if not isinstance(v, str) or v.strip() == "":
                raise SystemExit(f"row {i}: invalid {col} value: {v!r}")

        for col in ["total_cost_eth", "total_cost_usd"]:
            v = row.get(col)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise SystemExit(f"row {i}: invalid numeric type for {col}: {type(v).__name__}")
            fv = float(v)
            if not math.isfinite(fv):
                raise SystemExit(f"row {i}: non-finite value for {col}")
            if fv < 0:
                raise SystemExit(f"row {i}: negative value for {col}: {fv}")


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "pyarrow is required to write parquet output. "
            "Install it (e.g. `python -m pip install pyarrow`) and rerun."
        ) from exc

    ensure_dir(path.parent)
    table = pa.Table.from_pydict(
        {
            "date_utc": [str(r["date_utc"]) for r in rows],
            "rollup_id": [str(r["rollup_id"]) for r in rows],
            "l2beat_slug": [str(r["l2beat_slug"]) for r in rows],
            "total_cost_eth": [float(r["total_cost_eth"]) for r in rows],
            "total_cost_usd": [float(r["total_cost_usd"]) for r in rows],
        },
        schema=pa.schema(
            [
                pa.field("date_utc", pa.string(), nullable=False),
                pa.field("rollup_id", pa.string(), nullable=False),
                pa.field("l2beat_slug", pa.string(), nullable=False),
                pa.field("total_cost_eth", pa.float64(), nullable=False),
                pa.field("total_cost_usd", pa.float64(), nullable=False),
            ]
        ),
    )
    pq.write_table(table, path, compression="zstd")


def _filter_rows_for_sample(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    allowed = set(SAMPLE_ROLLUPS)
    for row in rows:
        rollup_id = str(row.get("rollup_id", ""))
        if rollup_id not in allowed:
            continue
        d = _parse_date(str(row.get("date_utc", "")), label="date_utc")
        if d < SAMPLE_WINDOW_START or d > SAMPLE_WINDOW_END:
            continue
        out.append(row)
    out.sort(key=lambda r: (str(r["date_utc"]), str(r["rollup_id"])))
    return out


def _write_sample_csv_append_only(path: Path, rows: list[dict[str, object]]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing sample: {path}")
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(REQUIRED_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "date_utc": str(row["date_utc"]),
                    "rollup_id": str(row["rollup_id"]),
                    "l2beat_slug": str(row["l2beat_slug"]),
                    "total_cost_eth": format(float(row["total_cost_eth"]), "f"),
                    "total_cost_usd": format(float(row["total_cost_usd"]), "f"),
                }
            )


def cmd_run(
    *,
    run_date: date | None,
    from_snapshot: Path | None,
    registry_path: Path,
    out_processed: Path,
    start_date: date,
    end_date: date,
    filter_type: str,
    write_sample: bool,
    sample_out: Path,
    write_raw_manifest: bool,
    write_processed_manifest: bool,
) -> int:
    if (run_date is None) == (from_snapshot is None):
        raise SystemExit("Provide exactly one of --run-date (fetch) or --from-snapshot (offline rebuild).")

    registry_by_slug = load_registry(registry_path)
    in_scope_rows = [
        row
        for row in registry_by_slug.values()
        if row.in_scope and row.status != "deprecated" and row.overlaps(start=start_date, end=end_date)
    ]
    requested_slugs = sorted({row.l2beat_slug for row in in_scope_rows})
    if not requested_slugs:
        raise SystemExit("No in-scope L2BEAT slugs found in registry for the requested date window")

    snapshot_dir: Path
    as_of: date
    snapshot_meta: dict[str, object]
    raw_manifest_path: Path | None = None

    if run_date is not None:
        as_of = run_date
        start_ts, end_ts = _window_to_range_seconds(start_date=start_date, end_date=end_date)
        snap = _snapshot_full(
            run_date=run_date,
            start_ts=start_ts,
            end_ts=end_ts,
            filter_type=filter_type,
            requested_slugs=requested_slugs,
        )
        snapshot_dir = snap.snapshot_dir
        snapshot_meta = {
            "requested_slugs": snap.requested_slugs,
            "available_slugs": snap.available_slugs,
            "missing_from_table_slugs": snap.missing_from_table_slugs,
            "written_files": [str(p.relative_to(REPO_ROOT)) for p in snap.written_files],
            "reused_files": [str(p.relative_to(REPO_ROOT)) for p in snap.reused_files],
        }
        if write_raw_manifest:
            raw_manifest_path = _write_raw_manifest(
                source="l2beat",
                snapshot_dir=snapshot_dir.relative_to(REPO_ROOT),
                as_of=as_of,
            )
    else:
        assert from_snapshot is not None
        snapshot_dir = from_snapshot if from_snapshot.is_absolute() else (REPO_ROOT / from_snapshot)
        if not snapshot_dir.exists():
            raise SystemExit(f"--from-snapshot not found: {snapshot_dir}")
        try:
            as_of = _parse_date(snapshot_dir.name, label="snapshot_dir")
        except SystemExit:
            as_of = date.today()
        snapshot_meta = {
            "requested_slugs": requested_slugs,
            "available_slugs": None,
            "missing_from_table_slugs": [],
            "written_files": [],
            "reused_files": [],
        }

    norm = _normalize_from_snapshot(
        snapshot_dir=snapshot_dir,
        registry_by_slug=registry_by_slug,
        start_date=start_date,
        end_date=end_date,
    )
    _assert_required_schema(norm.rows)
    _write_parquet(out_processed, norm.rows)

    sample_rows = _filter_rows_for_sample(norm.rows)
    if write_sample:
        if not sample_rows:
            raise SystemExit("Sample filter produced zero rows; refusing to write empty sample")
        _write_sample_csv_append_only(sample_out, sample_rows)

    if write_processed_manifest:
        manifest_inputs: list[Path] = []
        if raw_manifest_path is not None and raw_manifest_path.exists():
            manifest_inputs.append(raw_manifest_path)
        else:
            candidate = REPO_ROOT / "data" / "raw_manifest" / f"l2beat_{as_of.isoformat()}.json"
            if candidate.exists():
                manifest_inputs.append(candidate)
        manifest_inputs.append(registry_path)

        manifest_outputs = [out_processed]
        if write_sample:
            manifest_outputs.append(sample_out)
        meta = {
            "source": "l2beat",
            "endpoints": {
                "costs_page_url": L2BEAT_COSTS_PAGE_URL,
                "trpc_base_url": L2BEAT_TRPC_BASE_URL,
                "procedures": [TABLE_PROCEDURE, PROJECT_CHART_PROCEDURE],
            },
            "chart_component_indexes": {
                "eth_total_components": list(ETH_COMPONENT_INDEXES),
                "usd_total_components": list(USD_COMPONENT_INDEXES),
            },
            "date_range_utc": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "sample_window_utc": {
                "start": SAMPLE_WINDOW_START.isoformat(),
                "end": SAMPLE_WINDOW_END.isoformat(),
            },
            "sample_rollups": list(SAMPLE_ROLLUPS),
            "normalization_counts": norm.counts,
            "sample_rows_emitted": len(sample_rows),
            "snapshot": snapshot_meta,
        }
        _write_processed_manifest(
            name="l2beat_costs_daily",
            as_of=as_of,
            inputs=[p.relative_to(REPO_ROOT) if p.is_absolute() else p for p in manifest_inputs],
            outputs=[p.relative_to(REPO_ROOT) if p.is_absolute() else p for p in manifest_outputs],
            meta=meta,
        )

    print(
        json.dumps(
            {
                "ok": True,
                "as_of_utc_date": as_of.isoformat(),
                "snapshot_dir": str(snapshot_dir),
                "out_processed": str(out_processed),
                "normalization_counts": norm.counts,
                "sample": {
                    "rows": len(sample_rows),
                    "out": str(sample_out) if write_sample else None,
                },
                "snapshot": snapshot_meta,
                "raw_manifest": str(raw_manifest_path) if raw_manifest_path else None,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="l2beat_fetch.py")
    p.add_argument("--discover", action="store_true", help="Print curlable discovery metadata and exit")
    p.add_argument("--run-date", default=None, help="UTC run date for snapshot folder naming (YYYY-MM-DD)")
    p.add_argument("--from-snapshot", default=None, help="Offline mode: path to existing raw snapshot dir")
    p.add_argument("--mode", choices=["full", "table", "chart", "projectChart"], default="full")
    p.add_argument(
        "--filter-type",
        choices=["rollups", "validiumsAndOptimiums", "others", "notReviewed"],
        default="rollups",
    )
    p.add_argument("--project-id", default=None, help="L2BEAT project id/slug (required for mode=projectChart)")
    p.add_argument("--range-start-ts", type=int, default=None, help="Optional UNIX timestamp (seconds) start")
    p.add_argument("--range-end-ts", type=int, default=None, help="Optional UNIX timestamp (seconds) end")
    p.add_argument("--registry", default="registry/rollup_registry_v1.csv")
    p.add_argument("--start-date", default="2022-01-01", help="Start date (UTC) for normalized panel (YYYY-MM-DD)")
    p.add_argument(
        "--end-date",
        default=None,
        help="End date (UTC) for normalized panel (YYYY-MM-DD; default=run-date/today)",
    )
    p.add_argument("--out-processed", default="data/processed/l2beat/l2beat_costs_daily.parquet")
    p.add_argument(
        "--write-sample",
        action="store_true",
        help="Write committed golden sample CSV (append-only; refuses overwrite).",
    )
    p.add_argument("--sample-out", default="data/samples/l2beat/l2beat_costs_daily_sample.csv")
    p.add_argument(
        "--write-raw-manifest",
        action="store_true",
        help="Write data/raw_manifest/l2beat_<run-date>.json (requires --run-date).",
    )
    p.add_argument(
        "--write-processed-manifest",
        action="store_true",
        help="Write data/processed_manifest/l2beat_costs_daily_<as-of>.json.",
    )
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.discover:
        return cmd_discover()

    run_date = _parse_date(args.run_date, label="run_date") if args.run_date else None
    from_snapshot = Path(args.from_snapshot) if args.from_snapshot else None

    if args.mode != "full":
        if from_snapshot is not None:
            raise SystemExit("--from-snapshot is only supported with --mode full")
        if run_date is None:
            raise SystemExit("--run-date is required for snapshot modes (table/chart/projectChart)")
        return cmd_snapshot(
            run_date=run_date.isoformat(),
            mode=str(args.mode),
            filter_type=str(args.filter_type) if args.mode in {"table", "chart"} else None,
            project_id=str(args.project_id) if args.project_id else None,
            range_start=args.range_start_ts,
            range_end=args.range_end_ts,
        )

    if run_date is None and from_snapshot is None:
        raise SystemExit("Provide --run-date or --from-snapshot when --mode full")
    if args.write_raw_manifest and run_date is None:
        raise SystemExit("--write-raw-manifest requires --run-date")

    start_date = _parse_date(str(args.start_date), label="start_date")
    end_date = (
        _parse_date(str(args.end_date), label="end_date")
        if args.end_date
        else (run_date if run_date is not None else date.today())
    )
    return cmd_run(
        run_date=run_date,
        from_snapshot=from_snapshot,
        registry_path=(
            Path(args.registry) if Path(args.registry).is_absolute() else (REPO_ROOT / Path(args.registry))
        ),
        out_processed=(
            Path(args.out_processed)
            if Path(args.out_processed).is_absolute()
            else (REPO_ROOT / Path(args.out_processed))
        ),
        start_date=start_date,
        end_date=end_date,
        filter_type=str(args.filter_type),
        write_sample=bool(args.write_sample),
        sample_out=(
            Path(args.sample_out)
            if Path(args.sample_out).is_absolute()
            else (REPO_ROOT / Path(args.sample_out))
        ),
        write_raw_manifest=bool(args.write_raw_manifest),
        write_processed_manifest=bool(args.write_processed_manifest),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
