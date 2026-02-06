from __future__ import annotations

"""Offline self-test for on-chain fee-component math (incl. blob tx fallback).

This script reads deterministic fixtures and asserts exact integer matches.

Exit codes:
- 0: pass
- 2: mismatch
- 3: missing inputs
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.etl.l1_fee_components import compute_fee_components_wei  # noqa: E402


DEFAULT_FIXTURE = REPO_ROOT / "data" / "samples" / "l1" / "fixtures" / "blob_tx_fee_components_v1.json"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(3)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON fixture: {path} ({exc.msg})") from exc


def _require_int_or_none(value: Any, *, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise SystemExit(f"Invalid {label} (bool is not int): {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return None
        return int(s)
    raise SystemExit(f"Invalid {label} type: {type(value)}")


def run_selftest(*, fixture_path: Path) -> int:
    payload = _load_json(fixture_path)
    if not isinstance(payload, dict):
        raise SystemExit(f"Fixture must be a JSON object: {fixture_path}")
    if payload.get("schema_version") != 1:
        raise SystemExit(f"Unexpected fixture schema_version (expected 1): {fixture_path}")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SystemExit(f"Fixture missing non-empty cases list: {fixture_path}")

    failures: list[dict[str, Any]] = []

    for case in cases:
        if not isinstance(case, dict):
            continue
        name = str(case.get("name") or "<unnamed>")
        inputs = case.get("inputs")
        expected = case.get("expected")
        if not isinstance(inputs, dict) or not isinstance(expected, dict):
            failures.append({"case": name, "reason": "invalid_case_shape"})
            continue

        try:
            got = compute_fee_components_wei(
                gas_used=int(inputs["gas_used"]),
                effective_gas_price_wei=int(inputs["effective_gas_price_wei"]),
                base_fee_per_gas_wei=int(inputs["base_fee_per_gas_wei"]),
                tx_type=inputs.get("tx_type"),
                receipt_blob_gas_used=_require_int_or_none(inputs.get("receipt_blob_gas_used"), label="receipt_blob_gas_used"),
                receipt_blob_gas_price_wei=_require_int_or_none(
                    inputs.get("receipt_blob_gas_price_wei"), label="receipt_blob_gas_price_wei"
                ),
                tx_blob_versioned_hashes_count=_require_int_or_none(
                    inputs.get("tx_blob_versioned_hashes_count"), label="tx_blob_versioned_hashes_count"
                ),
                block_excess_blob_gas=_require_int_or_none(inputs.get("block_excess_blob_gas"), label="block_excess_blob_gas"),
                tx_max_fee_per_blob_gas_wei=_require_int_or_none(
                    inputs.get("tx_max_fee_per_blob_gas_wei"), label="tx_max_fee_per_blob_gas_wei"
                ),
            )
        except Exception as exc:
            failures.append({"case": name, "reason": "exception", "error": str(exc)})
            continue

        checks = {
            "burn_base_wei": int(got.burn_base_wei),
            "tips_wei": int(got.tips_wei),
            "burn_blob_wei": int(got.burn_blob_wei),
            "blob_gas_used": int(got.blob_gas_used),
            "base_fee_per_blob_gas_wei": (int(got.base_fee_per_blob_gas_wei) if got.base_fee_per_blob_gas_wei is not None else None),
        }

        for k, got_val in checks.items():
            exp_val = expected.get(k)
            if exp_val != got_val:
                failures.append({"case": name, "field": k, "expected": exp_val, "got": got_val})

    ok = len(failures) == 0
    print(json.dumps({"ok": ok, "fixture": str(fixture_path), "failures": failures}, indent=2, sort_keys=True))
    return 0 if ok else 2


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="l1_fee_components_selftest.py")
    p.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="Path to fixture JSON")
    args = p.parse_args(argv[1:])

    fixture_path = Path(str(args.fixture))
    fixture_abs = fixture_path if fixture_path.is_absolute() else (REPO_ROOT / fixture_path)
    return run_selftest(fixture_path=fixture_abs)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
