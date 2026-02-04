from __future__ import annotations

import os
from pathlib import Path


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_bytes_append_only(path: Path, data: bytes) -> None:
    """Write bytes to path, refusing to overwrite existing files."""
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    ensure_dir(path.parent)

    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        raise FileExistsError(f"Refusing to overwrite existing temp file: {tmp}")

    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_text_append_only(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    write_bytes_append_only(path, text.encode(encoding))

