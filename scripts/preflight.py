from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import subprocess
from pathlib import Path


FULLSCALE_CRITICAL_MODULES = [
    "src/etl/prices_fetch.py",
    "src/etl/issuance_fetch.py",
    "src/etl/panel_build_daily_rollup_panel_v2.py",
    "src/validation/validate_cross_source.py",
]

_OUTPUT_PLACEHOLDER_PATTERNS = (
    re.compile(r"\.\.\."),
    re.compile(r"\bYYYY(?:-MM(?:-DD)?)?\b"),
    re.compile(r"<[^>]+>"),
    re.compile(r"[*?{}\[\]]"),
)


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


def _check_required_paths(root: Path, relpaths: list[str]) -> list[str]:
    missing: list[str] = []
    for relpath in relpaths:
        if not (root / relpath).exists():
            missing.append(relpath)
    return missing


def _parse_task_frontmatter(text: str) -> dict[str, object] | None:
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return None
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None

    data: dict[str, object] = {}
    current_list_key: str | None = None
    for raw_line in lines[1:end_idx]:
        line = raw_line.split("#", 1)[0].rstrip()
        if line.strip() == "":
            continue

        list_item_match = re.match(r"^\s*-\s+(.*)\s*$", line)
        if current_list_key is not None and list_item_match is not None:
            item = list_item_match.group(1).strip().strip("'\"")
            current_list = data.get(current_list_key)
            if isinstance(current_list, list):
                current_list.append(item)
            continue

        current_list_key = None
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        key = key.strip()
        rest = rest.strip()

        if rest == "":
            data[key] = []
            current_list_key = key
            continue

        if rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1].strip()
            if inner == "":
                data[key] = []
            else:
                items = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
                data[key] = items
            continue

        data[key] = rest.strip("'\"")

    return data


def _coerce_list(value: object) -> list[str]:
    if isinstance(value, list):
        out: list[str] = []
        for x in value:
            if isinstance(x, str):
                out.append(x)
        return out
    return []


def _is_checkable_output_path(output_path: str) -> bool:
    candidate = output_path.strip()
    if candidate == "":
        return False
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return False
    for pattern in _OUTPUT_PLACEHOLDER_PATTERNS:
        if pattern.search(candidate):
            return False
    return True


def _find_backlog_output_drift(root: Path) -> list[dict[str, object]]:
    backlog_dir = root / ".orchestrator" / "backlog"
    if not backlog_dir.exists():
        return []

    drift: list[dict[str, object]] = []
    for task_path in sorted(backlog_dir.glob("*.md")):
        if task_path.name == "README.md":
            continue
        frontmatter = _parse_task_frontmatter(task_path.read_text(encoding="utf-8")) or {}
        task_id_raw = frontmatter.get("task_id")
        task_id = task_id_raw if isinstance(task_id_raw, str) else task_path.stem
        outputs = _coerce_list(frontmatter.get("outputs"))
        checkable_outputs = [o for o in outputs if _is_checkable_output_path(o)]
        if len(checkable_outputs) == 0:
            continue
        if all((root / relpath).exists() for relpath in checkable_outputs):
            rel_task_path = str(task_path.relative_to(root))
            drift.append(
                {
                    "task_id": task_id,
                    "task_file": rel_task_path,
                    "outputs_checked": checkable_outputs,
                    "action": f"Update State in {rel_task_path} (ready_for_review or done) and run `make sweep`.",
                }
            )
    return drift


def _trim_output(text: str, max_chars: int = 4000) -> str:
    trimmed = text.strip()
    if len(trimmed) <= max_chars:
        return trimmed
    return trimmed[-max_chars:]


def _run_quality_gates(root: Path) -> dict[str, object]:
    cmd = [sys.executable, "scripts/quality_gates.py"]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return {"ok": False, "returncode": None, "command": " ".join(cmd), "error": str(exc)}

    details: dict[str, object] = {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "command": " ".join(cmd),
    }
    stdout_tail = _trim_output(result.stdout)
    stderr_tail = _trim_output(result.stderr)
    if stdout_tail != "":
        details["stdout_tail"] = stdout_tail
    if stderr_tail != "":
        details["stderr_tail"] = stderr_tail
    return details


def main(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="preflight.py")
    p.add_argument("--profile", choices=["base", "onchain", "bigquery", "fullscale"], default="base")
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

    if args.profile == "fullscale":
        missing_modules = _check_required_paths(root, FULLSCALE_CRITICAL_MODULES)
        if missing_modules:
            ok = False
        details["missing_pipeline_modules"] = missing_modules

        backlog_drift = _find_backlog_output_drift(root)
        if backlog_drift:
            ok = False
        details["control_plane_drift"] = backlog_drift

        quality_gates = _run_quality_gates(root)
        if not bool(quality_gates.get("ok", False)):
            ok = False
        details["quality_gates"] = quality_gates

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
            if args.profile == "fullscale":
                missing_modules = details.get("missing_pipeline_modules") or []
                if isinstance(missing_modules, list) and len(missing_modules) > 0:
                    print(f"missing_pipeline_modules: {', '.join(str(x) for x in missing_modules)}")

                control_plane_drift = details.get("control_plane_drift") or []
                if isinstance(control_plane_drift, list) and len(control_plane_drift) > 0:
                    print("control_plane_drift:")
                    for row in control_plane_drift:
                        if not isinstance(row, dict):
                            continue
                        task_id = str(row.get("task_id", "unknown"))
                        task_file = str(row.get("task_file", ""))
                        action = str(row.get("action", ""))
                        print(f"- {task_id}: {task_file}")
                        if action:
                            print(f"  action: {action}")

                quality_gates = details.get("quality_gates")
                if isinstance(quality_gates, dict) and not bool(quality_gates.get("ok", False)):
                    print(f"quality_gates_failed: rc={quality_gates.get('returncode')}")
                    stdout_tail = quality_gates.get("stdout_tail")
                    stderr_tail = quality_gates.get("stderr_tail")
                    if isinstance(stdout_tail, str) and stdout_tail.strip():
                        print("quality_gates_stdout_tail:")
                        print(stdout_tail)
                    if isinstance(stderr_tail, str) and stderr_tail.strip():
                        print("quality_gates_stderr_tail:")
                        print(stderr_tail)
            if args.profile == "bigquery" and args.bq_smoke:
                err = details.get("bq_smoke_error")
                if err:
                    print("bq_smoke_error:")
                    print(err)

    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    main(sys.argv)
