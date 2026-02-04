from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shlex
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_within_repo(root: Path, target: Path) -> Path:
    try:
        return target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"path must be inside repo root: {root} (got {target})") from exc


def _parse_utc_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid --as-of date (expected YYYY-MM-DD): {value!r}") from exc


def _git_sha(root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    sha = r.stdout.strip()
    return sha or None


def _materialize_paths(root: Path, paths: list[Path], *, label: str) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        abs_p = p if p.is_absolute() else (root / p)
        if not abs_p.exists():
            raise SystemExit(f"{label} path does not exist: {abs_p}")
        out.append(abs_p)
    return out


def _collect_file_entries(root: Path, abs_paths: list[Path]) -> list[dict[str, object]]:
    seen: set[str] = set()
    entries: list[dict[str, object]] = []

    for abs_p in abs_paths:
        candidates: list[Path]
        if abs_p.is_dir():
            candidates = [p for p in abs_p.rglob("*") if p.is_file()]
        else:
            if not abs_p.is_file():
                raise SystemExit(f"Expected file or directory; got: {abs_p}")
            candidates = [abs_p]

        for p in candidates:
            rel = _ensure_within_repo(root, p)
            rel_str = str(rel)
            if rel_str in seen:
                continue
            seen.add(rel_str)
            entries.append(
                {
                    "path": rel_str,
                    "sha256": _sha256_file(p),
                    "bytes": p.stat().st_size,
                }
            )

    entries.sort(key=lambda d: str(d["path"]))
    return entries


def build_manifest(
    *,
    name: str,
    as_of: date,
    inputs: list[Path],
    outputs: list[Path],
    command: str,
    meta: dict[str, object] | None,
) -> dict[str, object]:
    root = _repo_root()

    abs_inputs = _materialize_paths(root, inputs, label="input")
    abs_outputs = _materialize_paths(root, outputs, label="output")

    now = datetime.now(timezone.utc)
    script_rel = _ensure_within_repo(root, Path(__file__).resolve())
    git_sha = _git_sha(root)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "name": name,
        "as_of_utc_date": as_of.isoformat(),
        "created_at_utc": now.isoformat(),
        "inputs": _collect_file_entries(root, abs_inputs),
        "transform": {
            "script_path": str(script_rel),
            "git_sha": git_sha,
            "command": command,
        },
        "outputs": _collect_file_entries(root, abs_outputs),
        "environment": {
            "python_version": sys.version.split()[0],
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
    }
    if meta is not None:
        manifest["meta"] = meta
    return manifest


def _render_command(cmd_tokens: list[str]) -> str:
    if not cmd_tokens:
        raise SystemExit("Missing command. Provide it after --, e.g. -- python src/etl/foo.py --run-date ...")
    return " ".join(shlex.quote(t) for t in cmd_tokens)


def _load_meta_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"--meta-json not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--meta-json is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("--meta-json must contain a JSON object at the top level")
    return payload


def main(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="make_processed_manifest.py")
    p.add_argument("name", help="Manifest name prefix, e.g. daily_rollup_panel_v1")
    p.add_argument("--as-of", dest="as_of", required=True, help="UTC as-of date (YYYY-MM-DD)")
    p.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="Input manifest path(s) (e.g. data/raw_manifest/<source>_YYYY-MM-DD.json) and/or other processed manifests.",
    )
    p.add_argument(
        "--outputs",
        nargs="+",
        required=True,
        help="Output file and/or directory paths produced by the transform (inside the repo).",
    )
    p.add_argument("--meta-json", dest="meta_json", default=None, help="Optional JSON file to store under manifest.meta")
    p.add_argument("--out", dest="out_path", default=None, help="Optional output path for the manifest JSON (inside repo)")

    # argparse + positional REMAINDER has surprising parsing behavior (optionals after positionals are treated as
    # positional args). We manually split at `--` to keep UX consistent with make_raw_manifest.py.
    if "--" not in argv:
        raise SystemExit("Missing command separator `--`. Example: -- python src/etl/foo.py ...")
    sep_idx = argv.index("--")
    args = p.parse_args(argv[1:sep_idx])
    command_tokens = argv[sep_idx + 1 :]

    as_of = _parse_utc_date(args.as_of)
    command = _render_command(command_tokens)
    meta = _load_meta_json(Path(args.meta_json)) if args.meta_json else None

    inputs = [Path(x) for x in args.inputs]
    outputs = [Path(x) for x in args.outputs]
    manifest = build_manifest(name=args.name, as_of=as_of, inputs=inputs, outputs=outputs, command=command, meta=meta)

    root = _repo_root()
    out_dir = root / "data/processed_manifest"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = Path(args.out_path) if args.out_path else (out_dir / f"{args.name}_{as_of.isoformat()}.json")
    out_abs = out_path if out_path.is_absolute() else (root / out_path)
    _ensure_within_repo(root, out_abs)
    if out_abs.exists():
        raise SystemExit(f"Refusing to overwrite existing manifest: {out_abs}")
    out_abs.parent.mkdir(parents=True, exist_ok=True)

    out_abs.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out_abs}")


if __name__ == "__main__":
    main(sys.argv)
