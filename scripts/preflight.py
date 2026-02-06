from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _check_tools(tools: list[str]) -> list[str]:
    missing: list[str] = []
    for t in tools:
        if shutil.which(t) is None:
            missing.append(t)
    return missing


def _check_env(required_vars: list[str]) -> list[str]:
    missing: list[str] = []
    for var in required_vars:
        val = os.environ.get(var)
        if val is None or val.strip() == "":
            missing.append(var)
    return missing


def main(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="preflight.py")
    p.add_argument("--profile", choices=["base", "onchain", "bigquery"], default="base")
    p.add_argument("--require", nargs="*", default=[], help="Additional environment variables to require")
    p.add_argument("--json", dest="json_output", action="store_true", help="Print a machine-readable JSON result")
    p.add_argument(
        "--bq-smoke",
        action="store_true",
        help="(bigquery profile) Run a tiny authenticated BigQuery query to verify bq access",
    )
    args = p.parse_args(argv[1:])

    root = _repo_root()
    cwd = Path.cwd().resolve()

    required_env = set(args.require)
    if args.profile == "onchain":
        required_env.add("ETH_RPC_URL")

    required_tools = ["python", "git"]
    if args.profile == "bigquery":
        required_tools.extend(["gcloud", "bq"])
    missing_tools = _check_tools(required_tools)
    missing_env = _check_env(sorted(required_env))

    ok = (len(missing_tools) == 0) and (len(missing_env) == 0)
    details = {
        "cwd": str(cwd),
        "repo_root": str(root),
        "profile": args.profile,
        "missing_tools": missing_tools,
        "missing_env": missing_env,
    }

    if args.profile == "bigquery" and shutil.which("gcloud") is not None:
        try:
            r = subprocess.run(["gcloud", "config", "get-value", "project"], check=True, capture_output=True, text=True)
            details["gcloud_project"] = r.stdout.strip() or None
        except Exception:
            details["gcloud_project"] = None

    if args.profile == "bigquery" and args.bq_smoke and ok:
        try:
            r = subprocess.run(
                ["bq", "--quiet", "query", "--use_legacy_sql=false", "--format=prettyjson", "SELECT 1 AS ok"],
                check=False,
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                ok = False
                details["bq_smoke_ok"] = False
                details["bq_smoke_error"] = (r.stderr or "").strip() or (r.stdout or "").strip()
            else:
                details["bq_smoke_ok"] = True
        except Exception as exc:
            ok = False
            details["bq_smoke_ok"] = False
            details["bq_smoke_error"] = str(exc)

    if args.json_output:
        print(json.dumps({"ok": ok, "details": details}, indent=2, sort_keys=True))
    else:
        if ok:
            print("ok")
        else:
            print("fail")
            if missing_tools:
                print(f"missing_tools: {', '.join(missing_tools)}")
            if missing_env:
                print(f"missing_env: {', '.join(missing_env)}")
            if args.profile == "bigquery" and args.bq_smoke:
                err = details.get("bq_smoke_error")
                if err:
                    print("bq_smoke_error:")
                    print(err)

    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    main(sys.argv)
