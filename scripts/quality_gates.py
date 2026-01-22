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
        Path("contracts/instances/benchmark_small"),
        Path("docs"),
        Path(".orchestrator"),
        Path(".orchestrator/AGENTS.md"),
        Path(".orchestrator/workstreams.md"),
        Path("data"),
        Path("data/AGENTS.md"),
        Path("data/samples"),
        Path("reports"),
        Path("reports/AGENTS.md"),
        Path("reports/catalog.yaml"),
        Path("scripts/quality_gates.py"),
        Path("scripts/AGENTS.md"),
        Path("src"),
        Path("src/AGENTS.md"),
    ]
    missing = [str(p) for p in required if not p.exists()]
    return GateResult(ok=(len(missing) == 0), details={"missing": missing})


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

    for field in ("Name", "Formula", "Units"):
        if re.search(rf"^\s*-\s*{field}:\s*$", text, flags=re.MULTILINE):
            failures.append(f"primary_metric_{field.lower()}_blank")

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

        for heading in ("## Status", "## Notes / Decisions"):
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


def main() -> None:
    results = {
        "repo_structure": gate_repo_structure(),
        "project_contract": gate_project_contract(),
        "environment": gate_environment(),
        "protocol_complete": gate_protocol_complete(),
        "model_spec_complete": gate_model_spec_complete(),
        "workstreams_complete": gate_workstreams_complete(),
        "task_hygiene": gate_task_hygiene(),
    }
    ok = all(r.ok for r in results.values())
    for name, r in results.items():
        print(f"[{name}] ok={r.ok} details={r.details}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
