"""Quality gates for the research pipeline.

This file is intentionally a stub. Add checks as your pipeline grows.

Design principle: gates should be *fast* and *deterministic*.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class GateResult:
    ok: bool
    details: dict[str, object]


def gate_repo_structure() -> GateResult:
    required = [
        Path("docs/protocol.md"),
        Path("AGENTS.md"),
        Path(".orchestrator"),
    ]
    missing = [str(p) for p in required if not p.exists()]
    return GateResult(ok=(len(missing) == 0), details={"missing": missing})


def main() -> None:
    results = {
        "repo_structure": gate_repo_structure(),
    }
    ok = all(r.ok for r in results.values())
    for name, r in results.items():
        print(f"[{name}] ok={r.ok} details={r.details}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
