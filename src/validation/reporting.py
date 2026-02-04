from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXIT_OK = 0
EXIT_FAIL = 2
EXIT_MISSING_INPUTS = 3


@dataclass(frozen=True)
class ValidationFailure:
    check: str
    message: str
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"check": self.check, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def exit_code_for(*, ok: bool, missing_inputs: list[str] | None = None) -> int:
    if missing_inputs:
        return EXIT_MISSING_INPUTS
    return EXIT_OK if ok else EXIT_FAIL

