from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.etl.offchain.http import http_get  # noqa: E402


BLOBSCAN_DOCS_URL = "https://docs.blobscan.com/docs/api"
BLOBSCAN_API_BASE_URL = "https://api.blobscan.com/"


def cmd_discover() -> int:
    out: dict[str, object] = {
        "docs_url": BLOBSCAN_DOCS_URL,
        "api_base_url": BLOBSCAN_API_BASE_URL,
        "notes": [
            "Blobscan may require auth for some endpoints; prefer public endpoints first.",
            "If API is unavailable or requires auth and no token is available, block and fall back to on-chain aggregates.",
            "See data/samples/blobscan/README.md for project-required fields and policy.",
        ],
    }
    try:
        resp = http_get(BLOBSCAN_API_BASE_URL, timeout_seconds=20, retries=2)
        out["api_status"] = resp.status
    except Exception as exc:
        out["api_status"] = "unreachable"
        out["api_error"] = str(exc)

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_snapshot(*, run_date: str) -> int:
    # This script is intentionally limited to discovery at bootstrap time.
    # Full ingestion should be implemented after confirming a stable public endpoint and response schema.
    raise SystemExit(
        "Blobscan snapshot mode is not implemented yet. Run with --discover and update "
        "data/samples/blobscan/README.md with the final endpoint(s) and schema snapshot before implementing ingestion."
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="blobscan_fetch.py")
    p.add_argument("--discover", action="store_true", help="Print endpoint availability notes and exit")
    p.add_argument("--run-date", default=None, help="UTC run date for snapshot folder naming (YYYY-MM-DD)")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.discover:
        return cmd_discover()
    if not args.run_date:
        raise SystemExit("--run-date is required unless --discover is used")
    return cmd_snapshot(run_date=str(args.run_date))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

