import hashlib
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from scripts import quality_gates


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


@contextmanager
def _cwd(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _base_manifest(output_path: str, output_bytes: int, output_sha256: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "unit_dataset",
        "as_of_utc_date": "2026-02-06",
        "created_at_utc": "2026-02-06T12:00:00+00:00",
        "inputs": [
            {
                "path": "data/raw_manifest/source_2026-02-06.json",
                "sha256": "0" * 64,
                "bytes": 123,
            }
        ],
        "transform": {
            "script_path": "scripts/make_processed_manifest.py",
            "git_sha": "a" * 40,
            "command": "python src/etl/example.py --as-of 2026-02-06",
        },
        "outputs": [
            {
                "path": output_path,
                "sha256": output_sha256,
                "bytes": output_bytes,
            }
        ],
        "environment": {
            "python_version": "3.13.1",
            "python_implementation": "CPython",
            "platform": "test-platform",
        },
    }


class ProcessedManifestGateTest(unittest.TestCase):
    def _write_manifest(self, root: Path, payload: dict[str, object], name: str = "example_2026-02-06.json") -> Path:
        manifest_dir = root / "data" / "processed_manifest"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / name
        manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return manifest_path

    def test_gate_processed_manifest_consistency_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_path = root / "data" / "processed" / "panels" / "daily_rollup_panel.csv"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            payload_bytes = b"date_utc,rollup_id,l2_fees_eth,rent_paid_eth\n2024-01-01,base,1.0,0.2\n"
            out_path.write_bytes(payload_bytes)

            manifest = _base_manifest(
                output_path="data/processed/panels/daily_rollup_panel.csv",
                output_bytes=len(payload_bytes),
                output_sha256=_sha256_bytes(payload_bytes),
            )
            self._write_manifest(root, manifest)

            with _cwd(root):
                result = quality_gates.gate_processed_manifest_consistency()

            self.assertTrue(result.ok, msg=result.details)
            self.assertEqual(result.details["count"], 1)
            self.assertEqual(result.details["checked_outputs"], 1)
            self.assertEqual(result.details["failures"], [])

    def test_gate_processed_manifest_consistency_missing_required_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_path = root / "data" / "processed" / "x.csv"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_bytes = b"hello\n"
            out_path.write_bytes(out_bytes)

            manifest = _base_manifest(
                output_path="data/processed/x.csv",
                output_bytes=len(out_bytes),
                output_sha256=_sha256_bytes(out_bytes),
            )
            del manifest["transform"]
            self._write_manifest(root, manifest)

            with _cwd(root):
                result = quality_gates.gate_processed_manifest_consistency()

            self.assertFalse(result.ok)
            failures = result.details["failures"]
            self.assertIn("data/processed_manifest/example_2026-02-06.json:missing_keys:transform", failures)
            self.assertIn("data/processed_manifest/example_2026-02-06.json:transform_not_object", failures)

    def test_gate_processed_manifest_consistency_missing_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _base_manifest(
                output_path="data/nonvolatile/missing.csv",
                output_bytes=1,
                output_sha256="0" * 64,
            )
            self._write_manifest(root, manifest)

            with _cwd(root):
                result = quality_gates.gate_processed_manifest_consistency()

            self.assertFalse(result.ok)
            failures = result.details["failures"]
            self.assertIn(
                "data/processed_manifest/example_2026-02-06.json:outputs[0]:missing_output_file:data/nonvolatile/missing.csv",
                failures,
            )

    def test_gate_processed_manifest_consistency_skips_unchanged_volatile_missing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _base_manifest(
                output_path="data/processed/missing.csv",
                output_bytes=1,
                output_sha256="0" * 64,
            )
            self._write_manifest(root, manifest)

            with (
                _cwd(root),
                mock.patch.object(quality_gates, "_resolve_base_ref", return_value="origin/main"),
                mock.patch.object(quality_gates, "_git_changed_paths_against_base", return_value=(["src/etl/example.py"], None)),
            ):
                result = quality_gates.gate_processed_manifest_consistency()

            self.assertTrue(result.ok, msg=result.details)
            self.assertEqual(result.details["checked_outputs"], 0)
            self.assertEqual(result.details["skipped_volatile_outputs"], 1)
            self.assertEqual(result.details["failures"], [])

    def test_gate_processed_manifest_consistency_skips_changed_volatile_missing_output_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _base_manifest(
                output_path="data/processed/missing.csv",
                output_bytes=1,
                output_sha256="0" * 64,
            )
            self._write_manifest(root, manifest)

            with (
                _cwd(root),
                mock.patch.object(quality_gates, "_resolve_base_ref", return_value="origin/main"),
                mock.patch.object(
                    quality_gates,
                    "_git_changed_paths_against_base",
                    return_value=(["data/processed_manifest/example_2026-02-06.json"], None),
                ),
            ):
                result = quality_gates.gate_processed_manifest_consistency()

            self.assertTrue(result.ok, msg=result.details)
            self.assertEqual(result.details["checked_outputs"], 0)
            self.assertEqual(result.details["skipped_volatile_outputs"], 1)
            self.assertEqual(result.details["failures"], [])

    def test_gate_processed_manifest_consistency_blocks_changed_volatile_missing_output_in_strict_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _base_manifest(
                output_path="data/processed/missing.csv",
                output_bytes=1,
                output_sha256="0" * 64,
            )
            self._write_manifest(root, manifest)

            with (
                _cwd(root),
                mock.patch.dict(os.environ, {"GATE_STRICT_VOLATILE_OUTPUTS": "1"}, clear=False),
                mock.patch.object(quality_gates, "_resolve_base_ref", return_value="origin/main"),
                mock.patch.object(
                    quality_gates,
                    "_git_changed_paths_against_base",
                    return_value=(["data/processed_manifest/example_2026-02-06.json"], None),
                ),
            ):
                result = quality_gates.gate_processed_manifest_consistency()

            self.assertFalse(result.ok)
            self.assertIn(
                "data/processed_manifest/example_2026-02-06.json:outputs[0]:missing_output_file:data/processed/missing.csv",
                result.details["failures"],
            )

    def test_gate_processed_manifest_consistency_skips_unchanged_volatile_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_path = root / "data" / "processed" / "mismatch.csv"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            payload_bytes = b"a,b\n1,2\n"
            out_path.write_bytes(payload_bytes)

            manifest = _base_manifest(
                output_path="data/processed/mismatch.csv",
                output_bytes=len(payload_bytes) + 100,
                output_sha256="0" * 64,
            )
            self._write_manifest(root, manifest)

            with (
                _cwd(root),
                mock.patch.object(quality_gates, "_resolve_base_ref", return_value="origin/main"),
                mock.patch.object(quality_gates, "_git_changed_paths_against_base", return_value=([], None)),
            ):
                result = quality_gates.gate_processed_manifest_consistency()

            self.assertTrue(result.ok, msg=result.details)
            self.assertEqual(result.details["checked_outputs"], 0)
            self.assertEqual(result.details["skipped_volatile_outputs"], 1)
            self.assertEqual(result.details["failures"], [])

    def test_gate_processed_manifest_consistency_sha_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_path = root / "data" / "processed" / "mismatch.csv"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            payload_bytes = b"a,b\n1,2\n"
            out_path.write_bytes(payload_bytes)

            manifest = _base_manifest(
                output_path="data/processed/mismatch.csv",
                output_bytes=len(payload_bytes),
                output_sha256="0" * 64,
            )
            self._write_manifest(root, manifest)

            with _cwd(root):
                result = quality_gates.gate_processed_manifest_consistency()

            self.assertFalse(result.ok)
            joined = "\n".join(result.details["failures"])
            self.assertIn("data/processed_manifest/example_2026-02-06.json:outputs[0]:sha256_mismatch:", joined)

    def test_gate_processed_manifest_consistency_bytes_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_path = root / "data" / "processed" / "bytes.csv"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            payload_bytes = b"x,y\n3,4\n"
            out_path.write_bytes(payload_bytes)

            manifest = _base_manifest(
                output_path="data/processed/bytes.csv",
                output_bytes=len(payload_bytes) + 10,
                output_sha256=_sha256_bytes(payload_bytes),
            )
            self._write_manifest(root, manifest)

            with _cwd(root):
                result = quality_gates.gate_processed_manifest_consistency()

            self.assertFalse(result.ok)
            joined = "\n".join(result.details["failures"])
            self.assertIn("data/processed_manifest/example_2026-02-06.json:outputs[0]:bytes_mismatch:", joined)


if __name__ == "__main__":
    unittest.main()
