from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.etl.offchain.files import write_text_append_only  # noqa: E402
from src.etl.offchain.http import http_get_text  # noqa: E402
from src.etl.offchain.trpc import trpc_query_batch1  # noqa: E402


L2BEAT_COSTS_PAGE_URL = "https://l2beat.com/scaling/costs"
L2BEAT_TRPC_BASE_URL = "https://l2beat.com/api/trpc"


def _parse_ssr_data_from_html(html: str) -> dict[str, Any]:
    m = re.search(r"window\.__SSR_DATA__\s*=\s*", html)
    if m is None:
        raise ValueError("Could not find window.__SSR_DATA__ in L2BEAT HTML (site structure changed?)")

    tail = html[m.end() :].lstrip()
    if not tail.startswith("{"):
        brace = tail.find("{")
        if brace == -1:
            raise ValueError("Could not find JSON object start for window.__SSR_DATA__")
        tail = tail[brace:]

    try:
        data, _end = json.JSONDecoder().raw_decode(tail)
    except json.JSONDecodeError as exc:
        raise ValueError("Could not decode window.__SSR_DATA__ JSON (site structure changed?)") from exc

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


def _write_raw_snapshot(*, out_dir: Path, filename: str, text: str) -> Path:
    out_path = out_dir / filename
    write_text_append_only(out_path, text, encoding="utf-8")
    return out_path


def cmd_discover() -> int:
    html = http_get_text(L2BEAT_COSTS_PAGE_URL, timeout_seconds=30)
    ssr = _parse_ssr_data_from_html(html)
    default_start, default_end = _infer_default_range_seconds(ssr)
    print(
        json.dumps(
            {
                "costs_page_url": L2BEAT_COSTS_PAGE_URL,
                "trpc_base_url": L2BEAT_TRPC_BASE_URL,
                "procedures_observed": ["costs.table", "costs.chart", "costs.projectChart"],
                "default_range_seconds": [default_start, default_end],
                "notes": "Use tRPC batch=1 input encoding; see data/samples/l2beat/README.md.",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_snapshot(*, run_date: str, mode: str, filter_type: str | None, project_id: str | None, range_start: int | None, range_end: int | None) -> int:
    out_dir = REPO_ROOT / "data" / "raw" / "l2beat" / run_date
    out_dir.mkdir(parents=True, exist_ok=True)

    start_ts: int
    end_ts: int
    if range_start is not None and range_end is not None:
        start_ts, end_ts = int(range_start), int(range_end)
    else:
        html = http_get_text(L2BEAT_COSTS_PAGE_URL, timeout_seconds=30)
        ssr = _parse_ssr_data_from_html(html)
        start_ts, end_ts = _infer_default_range_seconds(ssr)

    if mode == "table":
        if filter_type is None:
            raise SystemExit("--filter-type is required for mode=table")
        input_obj = {"range": [start_ts, end_ts], "filter": {"type": filter_type}}
        res = trpc_query_batch1(base_url=L2BEAT_TRPC_BASE_URL, procedure="costs.table", input_obj=input_obj)
        _write_raw_snapshot(out_dir=out_dir, filename=f"costs_table_{filter_type}.json", text=res.raw_response_text)
        return 0

    if mode == "chart":
        if filter_type is None:
            raise SystemExit("--filter-type is required for mode=chart")
        input_obj = {"range": [start_ts, end_ts], "filter": {"type": filter_type}}
        res = trpc_query_batch1(base_url=L2BEAT_TRPC_BASE_URL, procedure="costs.chart", input_obj=input_obj)
        _write_raw_snapshot(out_dir=out_dir, filename=f"costs_chart_{filter_type}.json", text=res.raw_response_text)
        return 0

    if mode == "projectChart":
        if project_id is None:
            raise SystemExit("--project-id is required for mode=projectChart")
        input_obj = {"range": [start_ts, end_ts], "projectId": project_id}
        res = trpc_query_batch1(base_url=L2BEAT_TRPC_BASE_URL, procedure="costs.projectChart", input_obj=input_obj)
        _write_raw_snapshot(out_dir=out_dir, filename=f"project_chart_{project_id}.json", text=res.raw_response_text)
        return 0

    raise SystemExit(f"Unknown mode: {mode}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="l2beat_fetch.py")
    p.add_argument("--discover", action="store_true", help="Print curlable discovery metadata and exit")
    p.add_argument("--run-date", default=None, help="UTC run date for snapshot folder naming (YYYY-MM-DD)")
    p.add_argument("--mode", choices=["table", "chart", "projectChart"], default="table")
    p.add_argument("--filter-type", choices=["rollups", "validiumsAndOptimiums", "others", "notReviewed"], default="rollups")
    p.add_argument("--project-id", default=None, help="L2BEAT project id/slug (required for mode=projectChart)")
    p.add_argument("--range-start-ts", type=int, default=None, help="Optional UNIX timestamp (seconds) start")
    p.add_argument("--range-end-ts", type=int, default=None, help="Optional UNIX timestamp (seconds) end")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.discover:
        return cmd_discover()

    if not args.run_date:
        raise SystemExit("--run-date is required unless --discover is used")

    return cmd_snapshot(
        run_date=str(args.run_date),
        mode=str(args.mode),
        filter_type=str(args.filter_type) if args.mode in {"table", "chart"} else None,
        project_id=str(args.project_id) if args.project_id else None,
        range_start=args.range_start_ts,
        range_end=args.range_end_ts,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
