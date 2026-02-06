import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import preflight


def _write_backlog_task(path: Path, task_id: str, outputs: list[str]) -> None:
    lines = [
        "---",
        f'task_id: "{task_id}"',
        "outputs:",
    ]
    for output in outputs:
        lines.append(f'  - "{output}"')
    lines.extend(
        [
            "---",
            f"# Task {task_id}",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class PreflightFullscaleHelpersTest(unittest.TestCase):
    def test_check_required_paths_returns_missing_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            existing = root / "src" / "etl" / "prices_fetch.py"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text("pass\n", encoding="utf-8")

            missing = preflight._check_required_paths(
                root,
                [
                    "src/etl/prices_fetch.py",
                    "src/etl/issuance_fetch.py",
                ],
            )

            self.assertEqual(missing, ["src/etl/issuance_fetch.py"])

    def test_is_checkable_output_path_filters_placeholders(self) -> None:
        self.assertTrue(preflight._is_checkable_output_path("src/etl/growthepie_fetch.py"))
        self.assertFalse(preflight._is_checkable_output_path("data/raw/growthepie/YYYY-MM-DD/..."))
        self.assertFalse(preflight._is_checkable_output_path("reports/<tag>/result.csv"))
        self.assertFalse(preflight._is_checkable_output_path("https://example.com/output.csv"))

    def test_find_backlog_output_drift_detects_fully_existing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backlog = root / ".orchestrator" / "backlog"
            backlog.mkdir(parents=True, exist_ok=True)
            (backlog / "README.md").write_text("# Backlog\n", encoding="utf-8")

            _write_backlog_task(
                backlog / "T001_complete.md",
                "T001",
                ["src/etl/a.py", "reports/a.md"],
            )
            _write_backlog_task(
                backlog / "T002_partial.md",
                "T002",
                ["src/etl/b.py", "reports/b.md"],
            )
            _write_backlog_task(
                backlog / "T003_placeholder.md",
                "T003",
                ["data/raw/vendor/YYYY-MM-DD/..."],
            )

            (root / "src" / "etl").mkdir(parents=True, exist_ok=True)
            (root / "reports").mkdir(parents=True, exist_ok=True)
            (root / "src" / "etl" / "a.py").write_text("print('a')\n", encoding="utf-8")
            (root / "reports" / "a.md").write_text("# a\n", encoding="utf-8")
            (root / "src" / "etl" / "b.py").write_text("print('b')\n", encoding="utf-8")

            drift = preflight._find_backlog_output_drift(root)

            self.assertEqual(len(drift), 1)
            self.assertEqual(drift[0]["task_id"], "T001")
            self.assertEqual(drift[0]["task_file"], ".orchestrator/backlog/T001_complete.md")
            self.assertEqual(drift[0]["outputs_checked"], ["src/etl/a.py", "reports/a.md"])

    def test_run_quality_gates_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            completed = subprocess.CompletedProcess(
                args=["python", "scripts/quality_gates.py"],
                returncode=0,
                stdout="ok\n",
                stderr="",
            )
            with mock.patch("scripts.preflight.subprocess.run", return_value=completed) as run_mock:
                result = preflight._run_quality_gates(root)

            self.assertTrue(result["ok"])
            self.assertEqual(result["returncode"], 0)
            run_mock.assert_called_once()
            self.assertEqual(run_mock.call_args.kwargs["cwd"], str(root))

    def test_run_quality_gates_failure_trims_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            completed = subprocess.CompletedProcess(
                args=["python", "scripts/quality_gates.py"],
                returncode=1,
                stdout=("x" * 5000) + "\n",
                stderr="failure\n",
            )
            with mock.patch("scripts.preflight.subprocess.run", return_value=completed):
                result = preflight._run_quality_gates(root)

            self.assertFalse(result["ok"])
            self.assertEqual(result["returncode"], 1)
            self.assertIn("stdout_tail", result)
            self.assertLessEqual(len(str(result["stdout_tail"])), 4000)
            self.assertEqual(result["stderr_tail"], "failure")


if __name__ == "__main__":
    unittest.main()
