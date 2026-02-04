"""Quality gates for the research pipeline.

Design principles:
- fast (target: <30s locally)
- deterministic (no web calls, no randomness)
- actionable failures (clear next step)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import platform
import sys
import json
import subprocess
import csv
import os
from urllib.parse import urlparse


@dataclass
class GateResult:
    ok: bool
    details: dict[str, object]

VALID_TASK_STATES = {"backlog", "active", "blocked", "ready_for_review", "done"}
VALID_PROJECT_MODES = {"empirical", "modeling", "hybrid"}
VALID_TASK_ROLES = {"Planner", "Worker", "Judge"}
VALID_TASK_PRIORITIES = {"low", "medium", "high"}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_project_mode(path: Path) -> str | None:
    """Parse a minimal YAML key: `mode: <value>` from contracts/project.yaml.

    We intentionally avoid external YAML dependencies in quality gates.
    """
    if not path.exists():
        return None
    for raw_line in _read_text(path).splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if not line.startswith("mode:"):
            continue
        value = line.split(":", 1)[1].strip().strip("'\"").lower()
        return value
    return None


def _parse_task_frontmatter(text: str) -> dict[str, object] | None:
    """Parse a minimal YAML frontmatter block (no external YAML dependency).

    Supports:
    - `key: value`
    - `key: [a, b]`
    - `key:` followed by indented `- item` lines
    """
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


def _section_has_content(text: str, heading: str) -> bool:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$", text, flags=re.MULTILINE)
    if match is None:
        return False
    after = text[match.end() :]
    for line in after.splitlines():
        if line.startswith("## "):
            return False
        if line.strip() == "":
            continue
        if re.search(r"[A-Za-z0-9]", line):
            return True
    return False


def gate_repo_structure() -> GateResult:
    required = [
        Path("AGENTS.md"),
        Path("CLAUDE.md"),
        Path("contracts"),
        Path("contracts/AGENTS.md"),
        Path("contracts/CHANGELOG.md"),
        Path("contracts/assumptions.md"),
        Path("contracts/decisions.md"),
        Path("contracts/project.yaml"),
        Path("contracts/schemas"),
        Path("docs"),
        Path(".orchestrator"),
        Path(".orchestrator/AGENTS.md"),
        Path(".orchestrator/ready_for_review"),
        Path(".orchestrator/workstreams.md"),
        Path("data"),
        Path("data/AGENTS.md"),
        Path("data/samples"),
        Path("data/processed_manifest"),
        Path("reports"),
        Path("reports/AGENTS.md"),
        Path("reports/catalog.yaml"),
        Path("scripts/quality_gates.py"),
        Path("scripts/AGENTS.md"),
        Path("src"),
        Path("src/AGENTS.md"),
        Path("tests"),
        Path("registry"),
        Path("registry/AGENTS.md"),
        Path("registry/CHANGELOG.md"),
        Path("registry/README.md"),
        Path("registry/rollup_registry_v1.csv"),
        Path("registry/schemas/batcher_addresses_json_v1.schema.json"),
    ]
    mode = _parse_project_mode(Path("contracts/project.yaml"))
    if mode in {"empirical", "hybrid"}:
        required.extend(
            [
                Path("docs/protocol.md"),
                Path("contracts/schemas/panel_schema.yaml"),
                Path("contracts/schemas/panel_schema_str_v1.yaml"),
                Path("contracts/schemas/panel_schema_decomp_v1.yaml"),
            ]
        )
    if mode in {"modeling", "hybrid"}:
        required.extend(
            [
                Path("contracts/instances"),
                Path("contracts/instances/benchmark_small"),
                Path("contracts/experiments"),
                Path("src/model"),
            ]
        )
    missing = [str(p) for p in required if not p.exists()]
    return GateResult(ok=(len(missing) == 0), details={"mode": mode, "missing": missing})


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ROLLUP_ID_RE = re.compile(r"^[a-z0-9_]+$")


def _is_valid_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return parsed.netloc != ""


def _validate_batcher_addresses_json(obj: object) -> list[str]:
    failures: list[str] = []
    if not isinstance(obj, dict):
        return ["top_level_not_object"]

    allowed_top_keys = {"schema_version", "state", "addresses", "notes"}
    extra_top_keys = sorted(k for k in obj.keys() if k not in allowed_top_keys)
    if extra_top_keys:
        failures.append(f"extra_top_keys:{','.join(extra_top_keys)}")

    if obj.get("schema_version") != 1:
        failures.append("schema_version_not_1")

    state = obj.get("state")
    if state not in {"unknown", "partial", "complete"}:
        failures.append("invalid_state")

    addresses = obj.get("addresses")
    if not isinstance(addresses, list):
        failures.append("addresses_not_list")
        addresses = []

    notes = obj.get("notes")
    if notes is not None and not isinstance(notes, str):
        failures.append("notes_not_string")

    allowed_addr_keys = {
        "address",
        "role",
        "evidence_url",
        "verified_utc",
        "start_date_utc",
        "end_date_utc",
        "notes",
    }
    required_addr_keys = {"address", "role", "evidence_url", "verified_utc"}
    allowed_roles = {"batcher", "poster", "proposer", "sequencer", "other"}

    for i, entry in enumerate(addresses):
        if not isinstance(entry, dict):
            failures.append(f"addresses[{i}]:not_object")
            continue

        extra_keys = sorted(k for k in entry.keys() if k not in allowed_addr_keys)
        if extra_keys:
            failures.append(f"addresses[{i}]:extra_keys:{','.join(extra_keys)}")

        missing = sorted(k for k in required_addr_keys if k not in entry)
        if missing:
            failures.append(f"addresses[{i}]:missing_keys:{','.join(missing)}")
            continue

        address = entry.get("address")
        if not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
            failures.append(f"addresses[{i}]:invalid_address")

        role = entry.get("role")
        if role not in allowed_roles:
            failures.append(f"addresses[{i}]:invalid_role")

        evidence_url = entry.get("evidence_url")
        if not isinstance(evidence_url, str) or not _is_valid_http_url(evidence_url):
            failures.append(f"addresses[{i}]:invalid_evidence_url")

        verified_utc = entry.get("verified_utc")
        if not isinstance(verified_utc, str) or _DATE_RE.fullmatch(verified_utc) is None:
            failures.append(f"addresses[{i}]:invalid_verified_utc")

        for date_key in ["start_date_utc", "end_date_utc"]:
            v = entry.get(date_key)
            if v is None:
                continue
            if not isinstance(v, str) or _DATE_RE.fullmatch(v) is None:
                failures.append(f"addresses[{i}]:invalid_{date_key}")

        entry_notes = entry.get("notes")
        if entry_notes is not None and not isinstance(entry_notes, str):
            failures.append(f"addresses[{i}]:notes_not_string")

    return failures


def gate_rollup_registry_integrity() -> GateResult:
    """Validate that the rollup registry is non-empty and machine-parseable.

    This gate prevents downstream ETL/tasks from implicitly assuming a populated
    registry and silently drifting on identifier semantics.
    """
    path = Path("registry/rollup_registry_v1.csv")
    if not path.exists():
        return GateResult(ok=False, details={"missing": str(path)})

    failures: list[str] = []
    total_rows = 0
    in_scope_rows = 0
    rollup_ids: set[str] = set()

    required_cols = {
        "rollup_id",
        "display_name",
        "type",
        "da_posting_method",
        "origin_key",
        "l2beat_slug",
        "in_scope",
        "batcher_addresses_json",
        "evidence_url",
        "verified_utc",
        "status",
        "start_date_utc",
        "end_date_utc",
    }

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return GateResult(ok=False, details={"path": str(path), "failures": ["missing_header"]})

        missing = sorted(required_cols - set(reader.fieldnames))
        if missing:
            failures.append(f"missing_columns:{','.join(missing)}")

        for row_idx, row in enumerate(reader, start=2):
            total_rows += 1

            rollup_id = (row.get("rollup_id") or "").strip()
            if rollup_id == "":
                failures.append(f"row{row_idx}:missing_rollup_id")
                continue
            if rollup_id in rollup_ids:
                failures.append(f"row{row_idx}:duplicate_rollup_id:{rollup_id}")
                continue
            rollup_ids.add(rollup_id)
            if _ROLLUP_ID_RE.fullmatch(rollup_id) is None:
                failures.append(f"row{row_idx}:invalid_rollup_id:{rollup_id}")

            raw_in_scope = (row.get("in_scope") or "").strip().lower()
            if raw_in_scope in {"true", "1", "yes", "y"}:
                in_scope = True
            elif raw_in_scope in {"false", "0", "no", "n", ""}:
                in_scope = False
            else:
                failures.append(f"row{row_idx}:invalid_in_scope:{raw_in_scope}")
                in_scope = False

            status = (row.get("status") or "").strip().lower() or "active"
            if status not in {"active", "inactive", "deprecated"}:
                failures.append(f"row{row_idx}:invalid_status:{status}")

            start_date = (row.get("start_date_utc") or "").strip()
            if start_date != "" and _DATE_RE.fullmatch(start_date) is None:
                failures.append(f"row{row_idx}:invalid_start_date_utc:{start_date}")

            end_date = (row.get("end_date_utc") or "").strip()
            if end_date != "" and _DATE_RE.fullmatch(end_date) is None:
                failures.append(f"row{row_idx}:invalid_end_date_utc:{end_date}")

            if status == "inactive" and end_date == "":
                failures.append(f"row{row_idx}:inactive_missing_end_date_utc")

            if in_scope:
                in_scope_rows += 1

                origin_key = (row.get("origin_key") or "").strip()
                if origin_key == "":
                    failures.append(f"row{row_idx}:missing_origin_key_for_in_scope")

                l2beat_slug = (row.get("l2beat_slug") or "").strip()
                if l2beat_slug == "":
                    failures.append(f"row{row_idx}:missing_l2beat_slug_for_in_scope")

                evidence_url = (row.get("evidence_url") or "").strip()
                if evidence_url == "":
                    failures.append(f"row{row_idx}:missing_evidence_url_for_in_scope")
                elif not _is_valid_http_url(evidence_url):
                    failures.append(f"row{row_idx}:invalid_evidence_url_for_in_scope")

                verified_utc = (row.get("verified_utc") or "").strip()
                if verified_utc == "":
                    failures.append(f"row{row_idx}:missing_verified_utc_for_in_scope")
                elif _DATE_RE.fullmatch(verified_utc) is None:
                    failures.append(f"row{row_idx}:invalid_verified_utc_for_in_scope:{verified_utc}")

                raw_json = (row.get("batcher_addresses_json") or "").strip()
                if raw_json == "":
                    failures.append(f"row{row_idx}:missing_batcher_addresses_json_for_in_scope")
                else:
                    try:
                        parsed = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        failures.append(f"row{row_idx}:batcher_addresses_json_invalid_json:{exc.msg}")
                    else:
                        json_failures = _validate_batcher_addresses_json(parsed)
                        for jf in json_failures:
                            failures.append(f"row{row_idx}:batcher_addresses_json:{jf}")

    if total_rows == 0:
        failures.append("registry_has_no_rows")
    if in_scope_rows == 0:
        failures.append("registry_has_no_in_scope_rows")

    return GateResult(
        ok=(len(failures) == 0),
        details={"path": str(path), "total_rows": total_rows, "in_scope_rows": in_scope_rows, "failures": failures},
    )


def gate_project_contract() -> GateResult:
    path = Path("contracts/project.yaml")
    if not path.exists():
        return GateResult(ok=False, details={"missing": str(path)})
    mode = _parse_project_mode(path)
    if mode is None:
        return GateResult(ok=False, details={"failures": ["missing_mode"]})
    if mode not in VALID_PROJECT_MODES:
        return GateResult(ok=False, details={"failures": [f"invalid_mode:{mode}"]})
    return GateResult(ok=True, details={"mode": mode})


def gate_environment() -> GateResult:
    """Validate that a pinned environment spec exists and report runtime versions."""
    env_spec_candidates = [
        Path("pyproject.toml"),
        Path("requirements.txt"),
        Path("requirements-dev.txt"),
        Path("environment.yml"),
        Path(".python-version"),
        Path(".devcontainer/devcontainer.json"),
    ]
    present = [str(p) for p in env_spec_candidates if p.exists()]
    if len(present) == 0:
        return GateResult(ok=False, details={"missing": [str(p) for p in env_spec_candidates]})

    python_version_file = Path(".python-version")
    pinned_python = None
    if python_version_file.exists():
        pinned_python = _read_text(python_version_file).strip() or None

    return GateResult(
        ok=True,
        details={
            "present_env_specs": present,
            "python_version": sys.version.split()[0],
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "pinned_python": pinned_python,
        },
    )


def gate_protocol_complete() -> GateResult:
    mode = _parse_project_mode(Path("contracts/project.yaml"))
    if mode == "modeling":
        return GateResult(ok=True, details={"skipped": True, "mode": mode})

    path = Path("docs/protocol.md")
    if not path.exists():
        return GateResult(ok=False, details={"missing": str(path)})
    text = _read_text(path)

    failures: list[str] = []

    mode_match = re.search(r"^\s*-\s*Mode:\s*(\w+)\s*$", text, flags=re.MULTILINE)
    if mode_match is None:
        failures.append("missing_mode_line")
    else:
        protocol_mode = mode_match.group(1).strip().lower()
        if mode is not None and protocol_mode != mode:
            failures.append(f"mode_mismatch:{protocol_mode}!={mode}")

    for field in ("Name", "Units"):
        if re.search(rf"^\s*-\s*{field}:\s*$", text, flags=re.MULTILINE):
            failures.append(f"primary_metric_{field.lower()}_blank")

    # Support both `- Formula:` and `- Formula (daily):` styles, but fail if left blank.
    if re.search(r"^\s*-\s*Formula[^:]*:\s*$", text, flags=re.MULTILINE):
        failures.append("primary_metric_formula_blank")

    required_sections = [
        "Rollup inclusion criteria",
        "Data source priority",
        "Known regime dates",
        "Validation tolerances",
    ]
    for heading in required_sections:
        if not _section_has_content(text, heading):
            failures.append(f"missing_or_empty_section:{heading}")

    return GateResult(ok=(len(failures) == 0), details={"failures": failures})


def gate_model_spec_complete() -> GateResult:
    mode = _parse_project_mode(Path("contracts/project.yaml"))
    if mode not in {"modeling", "hybrid"}:
        return GateResult(ok=True, details={"skipped": True, "mode": mode})

    candidates = [
        Path("contracts/model_spec.md"),
        Path("contracts/model_spec.yaml"),
        Path("contracts/model_spec.yml"),
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        return GateResult(ok=False, details={"missing": [str(p) for p in candidates]})

    if path.suffix.lower() in {".yml", ".yaml"}:
        # Minimal check: file exists and is non-empty (structure gates cover existence).
        text = _read_text(path)
        ok = bool(text.strip())
        return GateResult(ok=ok, details={"path": str(path), "empty": (not ok)})

    text = _read_text(path)
    required_sections = [
        "Objective / question",
        "Notation and sets",
        "Decision variables",
        "Constraints",
        "Objective function",
        "Assumptions (explicit)",
        "Baselines / benchmark cases",
        "Solver / method",
        "Outputs (required)",
    ]
    failures = [s for s in required_sections if not _section_has_content(text, s)]
    return GateResult(ok=(len(failures) == 0), details={"path": str(path), "missing_or_empty_sections": failures})


def gate_workstreams_complete() -> GateResult:
    path = Path(".orchestrator/workstreams.md")
    if not path.exists():
        return GateResult(ok=False, details={"missing": str(path)})
    text = _read_text(path)

    failures: list[str] = []
    rows_checked = 0
    for line in text.splitlines():
        if not re.match(r"^\|\s*W\d+\s+", line):
            continue
        rows_checked += 1
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            failures.append(f"malformed_row:{line.strip()}")
            continue

        workstream = cells[0]
        purpose = cells[1]
        owns_paths = cells[2]
        does_not_own = cells[3]

        if purpose == "":
            failures.append(f"blank_purpose:{workstream}")
        if owns_paths == "":
            failures.append(f"blank_owns_paths:{workstream}")
        if does_not_own == "":
            failures.append(f"blank_does_not_own:{workstream}")

    if rows_checked == 0:
        failures.append("no_workstream_rows_found")

    return GateResult(ok=(len(failures) == 0), details={"failures": failures})


def gate_task_hygiene() -> GateResult:
    failures: list[str] = []
    task_dirs = [
        Path(".orchestrator/backlog"),
        Path(".orchestrator/active"),
        Path(".orchestrator/ready_for_review"),
        Path(".orchestrator/blocked"),
        Path(".orchestrator/done"),
    ]

    task_files: list[Path] = []
    for task_dir in task_dirs:
        if not task_dir.exists():
            failures.append(f"missing_dir:{task_dir}")
            continue
        for p in task_dir.glob("*.md"):
            if p.name == "README.md":
                continue
            task_files.append(p)

    for path in sorted(task_files):
        text = _read_text(path)

        frontmatter = _parse_task_frontmatter(text)
        if frontmatter is None:
            failures.append(f"{path}:missing_yaml_frontmatter")
        else:
            required_keys = [
                "task_id",
                "title",
                "workstream",
                "role",
                "priority",
                "dependencies",
                "allowed_paths",
                "disallowed_paths",
                "outputs",
                "gates",
                "stop_conditions",
            ]
            for key in required_keys:
                if key not in frontmatter:
                    failures.append(f"{path}:frontmatter_missing_key:{key}")

            list_keys = [
                "dependencies",
                "allowed_paths",
                "disallowed_paths",
                "outputs",
                "gates",
                "stop_conditions",
            ]
            for key in list_keys:
                value = frontmatter.get(key)
                if not isinstance(value, list):
                    failures.append(f"{path}:frontmatter_key_not_list:{key}")

            task_id = frontmatter.get("task_id")
            if isinstance(task_id, str):
                if not path.name.startswith(task_id):
                    failures.append(f"{path}:frontmatter_task_id_mismatch:{task_id}")

            workstream = frontmatter.get("workstream")
            if isinstance(workstream, str) and not re.fullmatch(r"W\d+", workstream):
                failures.append(f"{path}:invalid_workstream:{workstream}")

            role = frontmatter.get("role")
            if isinstance(role, str) and role not in VALID_TASK_ROLES:
                failures.append(f"{path}:invalid_role:{role}")

            priority = frontmatter.get("priority")
            if isinstance(priority, str) and priority not in VALID_TASK_PRIORITIES:
                failures.append(f"{path}:invalid_priority:{priority}")

        required_headings = [
            "## Context",
            "## Inputs",
            "## Outputs",
            "## Success Criteria",
            "## Status",
            "## Notes / Decisions",
        ]
        for heading in required_headings:
            if heading not in text:
                failures.append(f"{path}:missing_heading:{heading}")

        state_match = re.search(r"^\s*-\s*State:\s*(.+)\s*$", text, flags=re.MULTILINE)
        if state_match is None:
            failures.append(f"{path}:missing_state")
        else:
            state = state_match.group(1).strip()
            if state not in VALID_TASK_STATES:
                failures.append(f"{path}:invalid_state:{state}")

        updated_match = re.search(
            r"^\s*-\s*Last updated:\s*(\d{4}-\d{2}-\d{2})\s*$",
            text,
            flags=re.MULTILINE,
        )
        if updated_match is None:
            failures.append(f"{path}:missing_last_updated")

    return GateResult(ok=(len(failures) == 0), details={"failures": failures})


def gate_task_dependencies() -> GateResult:
    failures: list[str] = []
    task_dirs = [
        Path(".orchestrator/backlog"),
        Path(".orchestrator/active"),
        Path(".orchestrator/ready_for_review"),
        Path(".orchestrator/blocked"),
        Path(".orchestrator/done"),
    ]

    task_files: list[Path] = []
    for task_dir in task_dirs:
        if not task_dir.exists():
            continue
        for p in task_dir.glob("*.md"):
            if p.name == "README.md":
                continue
            task_files.append(p)

    id_to_path: dict[str, Path] = {}
    deps_map: dict[str, list[str]] = {}

    for path in sorted(task_files):
        fm = _parse_task_frontmatter(_read_text(path)) or {}
        task_id = fm.get("task_id")
        deps = fm.get("dependencies")
        if not isinstance(task_id, str):
            continue
        if task_id in id_to_path:
            failures.append(f"duplicate_task_id:{task_id}:{id_to_path[task_id]}:{path}")
            continue
        id_to_path[task_id] = path
        deps_list: list[str] = []
        if isinstance(deps, list):
            deps_list = [d for d in deps if isinstance(d, str)]
        deps_map[task_id] = deps_list

    # Validate dependency IDs exist and are well-formed.
    for task_id, deps in deps_map.items():
        for dep in deps:
            if not re.fullmatch(r"T\d{3}", dep):
                failures.append(f"{id_to_path.get(task_id)}:invalid_dependency_id:{dep}")
                continue
            if dep == task_id:
                failures.append(f"{id_to_path.get(task_id)}:self_dependency:{dep}")
                continue
            if dep not in id_to_path:
                failures.append(f"{id_to_path.get(task_id)}:missing_dependency:{dep}")

    # Detect cycles (simple DFS).
    visiting: set[str] = set()
    visited: set[str] = set()

    def _dfs(node: str, stack: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            # cycle: include from first occurrence
            if node in stack:
                i = stack.index(node)
                cycle = stack[i:] + [node]
                failures.append(f"dependency_cycle:{'->'.join(cycle)}")
            return
        visiting.add(node)
        stack.append(node)
        for dep in deps_map.get(node, []):
            if dep in id_to_path:
                _dfs(dep, stack)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for task_id in sorted(id_to_path.keys()):
        _dfs(task_id, [])

    return GateResult(ok=(len(failures) == 0), details={"failures": failures})


def _git_changed_paths_against_base(base_ref: str) -> tuple[list[str], str | None]:
    try:
        cp2 = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if cp2.returncode != 0:
            return [], "git_diff_failed"
        paths = [p.strip() for p in (cp2.stdout or "").splitlines() if p.strip()]
        return paths, None
    except Exception:
        return [], "git_diff_exception"


def _resolve_base_ref(candidate_refs: list[str]) -> str | None:
    for ref in candidate_refs:
        try:
            cp = subprocess.run(
                ["git", "rev-parse", "--verify", ref],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            if cp.returncode == 0:
                return ref
        except Exception:
            continue
    return None


def gate_contract_change_discipline() -> GateResult:
    """If contracts/protocol change, require a decision log + contract changelog update.

    Best-effort: compares against a base ref if available. Deterministic and offline.
    """
    env_base = os.environ.get("GATE_BASE_REF")
    base_ref = env_base or _resolve_base_ref(["origin/main", "main"])
    if base_ref is None:
        return GateResult(ok=True, details={"skipped": True, "reason": "base_ref_missing", "candidates": ["origin/main", "main"]})

    changed, err = _git_changed_paths_against_base(base_ref)
    if err is not None:
        return GateResult(ok=True, details={"skipped": True, "reason": err, "base_ref": base_ref})

    def _is_contract_change(p: str) -> bool:
        if p == "docs/protocol.md":
            return True
        if p.startswith("contracts/") and p not in {"contracts/decisions.md", "contracts/CHANGELOG.md"}:
            return True
        return False

    contract_changed = any(_is_contract_change(p) for p in changed)
    if not contract_changed:
        return GateResult(ok=True, details={"base_ref": base_ref, "contract_changed": False})

    required = {"contracts/decisions.md", "contracts/CHANGELOG.md"}
    missing = sorted(r for r in required if r not in changed)
    ok = len(missing) == 0
    return GateResult(
        ok=ok,
        details={
            "base_ref": base_ref,
            "contract_changed": True,
            "missing_required_updates": missing,
        },
    )


def gate_registry_change_discipline() -> GateResult:
    """If registry files change, require registry/CHANGELOG.md update (best-effort diff)."""
    env_base = os.environ.get("GATE_BASE_REF")
    base_ref = env_base or _resolve_base_ref(["origin/main", "main"])
    if base_ref is None:
        return GateResult(ok=True, details={"skipped": True, "reason": "base_ref_missing", "candidates": ["origin/main", "main"]})

    changed, err = _git_changed_paths_against_base(base_ref)
    if err is not None:
        return GateResult(ok=True, details={"skipped": True, "reason": err, "base_ref": base_ref})

    registry_changed = any(p.startswith("registry/") and p != "registry/CHANGELOG.md" for p in changed)
    if not registry_changed:
        return GateResult(ok=True, details={"base_ref": base_ref, "registry_changed": False})

    ok = "registry/CHANGELOG.md" in changed
    return GateResult(
        ok=ok,
        details={"base_ref": base_ref, "registry_changed": True, "missing_registry_changelog": (not ok)},
    )


def gate_raw_manifest_validity() -> GateResult:
    """Validate any tracked raw provenance manifests under data/raw_manifest/.

    This does not require raw snapshots to be present or hashed during gating;
    it only validates that any committed manifest JSON files are well-formed and
    include required keys.
    """
    failures: list[str] = []
    manifest_dir = Path("data/raw_manifest")
    if not manifest_dir.exists():
        return GateResult(ok=False, details={"missing": str(manifest_dir)})

    manifest_paths = sorted(manifest_dir.glob("*.json"))
    required_top_keys = {"source", "fetched_at_utc", "command", "files"}
    required_file_keys = {"path", "sha256", "bytes"}

    for path in manifest_paths:
        try:
            data = json.loads(_read_text(path))
        except json.JSONDecodeError as exc:
            failures.append(f"{path}:invalid_json:{exc}")
            continue

        if not isinstance(data, dict):
            failures.append(f"{path}:top_level_not_object")
            continue

        missing_keys = sorted(k for k in required_top_keys if k not in data)
        if missing_keys:
            failures.append(f"{path}:missing_keys:{','.join(missing_keys)}")
            continue

        files = data.get("files")
        if not isinstance(files, list):
            failures.append(f"{path}:files_not_list")
            continue

        for i, entry in enumerate(files):
            if not isinstance(entry, dict):
                failures.append(f"{path}:files[{i}]:not_object")
                continue
            missing_entry_keys = sorted(k for k in required_file_keys if k not in entry)
            if missing_entry_keys:
                failures.append(
                    f"{path}:files[{i}]:missing_keys:{','.join(missing_entry_keys)}"
                )
                continue
            sha = entry.get("sha256")
            if isinstance(sha, str) and not re.fullmatch(r"[0-9a-f]{64}", sha):
                failures.append(f"{path}:files[{i}]:invalid_sha256")

    return GateResult(
        ok=(len(failures) == 0),
        details={"count": len(manifest_paths), "failures": failures},
    )


def gate_panel_schema_nonempty() -> GateResult:
    mode = _parse_project_mode(Path("contracts/project.yaml"))
    if mode == "modeling":
        return GateResult(ok=True, details={"skipped": True, "mode": mode})

    path = Path("contracts/schemas/panel_schema_str_v1.yaml")
    if not path.exists():
        return GateResult(ok=False, details={"missing": str(path), "mode": mode})

    for raw_line in _read_text(path).splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if re.match(r"^[A-Za-z0-9_-]+\s*:", line):
            return GateResult(ok=True, details={"path": str(path), "mode": mode})
    return GateResult(ok=False, details={"path": str(path), "mode": mode, "failure": "comment_only"})


def gate_sample_panel_integrity() -> GateResult:
    """Best-effort integrity checks for committed golden samples (if present)."""
    sample = Path("data/samples/growthepie/vendor_daily_rollup_panel_sample.csv")
    if not sample.exists():
        return GateResult(ok=True, details={"skipped": True, "reason": "sample_missing"})

    required_cols = {"date_utc", "rollup_id", "l2_fees_eth", "rent_paid_eth"}
    failures: list[str] = []

    rows: list[dict[str, str]] = []
    with sample.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return GateResult(ok=False, details={"failures": ["missing_header"]})
        cols = set(reader.fieldnames)
        missing = sorted(c for c in required_cols if c not in cols)
        if missing:
            failures.append(f"missing_columns:{','.join(missing)}")
        for row in reader:
            rows.append(row)

    # Non-negativity (where parseable).
    for i, row in enumerate(rows[:2000]):  # safety cap for gates
        for col in ["l2_fees_eth", "rent_paid_eth", "profit_eth"]:
            if col not in row or row[col] in ("", None):
                continue
            try:
                v = float(row[col])
            except ValueError:
                failures.append(f"row{i}:invalid_number:{col}")
                continue
            if v < 0:
                failures.append(f"row{i}:negative:{col}")

    return GateResult(ok=(len(failures) == 0), details={"sample": str(sample), "failures": failures})


def main() -> None:
    results = {
        "repo_structure": gate_repo_structure(),
        "rollup_registry_integrity": gate_rollup_registry_integrity(),
        "project_contract": gate_project_contract(),
        "environment": gate_environment(),
        "protocol_complete": gate_protocol_complete(),
        "model_spec_complete": gate_model_spec_complete(),
        "panel_schema_nonempty": gate_panel_schema_nonempty(),
        "workstreams_complete": gate_workstreams_complete(),
        "task_hygiene": gate_task_hygiene(),
        "task_dependencies": gate_task_dependencies(),
        "contract_change_discipline": gate_contract_change_discipline(),
        "registry_change_discipline": gate_registry_change_discipline(),
        "raw_manifest_validity": gate_raw_manifest_validity(),
        "sample_panel_integrity": gate_sample_panel_integrity(),
    }
    ok = all(r.ok for r in results.values())
    for name, r in results.items():
        print(f"[{name}] ok={r.ok} details={r.details}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
