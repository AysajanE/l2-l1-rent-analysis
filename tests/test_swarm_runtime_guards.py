import argparse
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _load_swarm_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "swarm.py"
    spec = importlib.util.spec_from_file_location("swarm_under_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load scripts/swarm.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


swarm = _load_swarm_module()


class SwarmRuntimeGuardsTest(unittest.TestCase):
    def test_collect_changed_paths_includes_ignored_filesystem_mutation(self) -> None:
        status_before = [{"xy": "!!", "path": "data/tmp/", "old_path": ""}]
        status_after = [{"xy": "!!", "path": "data/tmp/", "old_path": ""}]

        status_delta, changed = swarm._collect_changed_paths(
            status_before=status_before,
            status_after=status_after,
            untracked_ignored_before={"data/tmp/": "fingerprint-a"},
            untracked_ignored_after={"data/tmp/": "fingerprint-b"},
            skip_prefixes=(),
        )

        self.assertEqual(status_delta, [])
        self.assertEqual(changed, ["data/tmp/"])

    def test_run_task_fails_closed_on_worker_nonzero_returncode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            task_file = repo / ".orchestrator" / "active" / "T999_guard.md"
            task_file.parent.mkdir(parents=True, exist_ok=True)
            task_file.write_text("placeholder\n", encoding="utf-8")

            task = swarm.Task(
                path=task_file,
                task_id="T999",
                title="runtime-guard-test",
                workstream="W0",
                role="worker",
                priority="high",
                dependencies=[],
                parallel_ok=False,
                allowed_paths=["scripts/"],
                disallowed_paths=[],
                outputs=[],
                gates=[],
                stop_conditions=[],
                required_env=[],
                state="active",
                last_updated=None,
            )

            args = argparse.Namespace(
                unattended=False,
                task_id="T999",
                remote="origin",
                base_branch="main",
                codex_model=None,
                codex_sandbox="workspace-write",
                max_worker_seconds=0,
                max_review_seconds=0,
                repair_context=None,
                create_pr=False,
                auto_merge=False,
                final_state="ready_for_review",
            )

            update_status_mock = mock.Mock()
            worker_rc = 23
            worker_cp = subprocess.CompletedProcess(args=["codex", "exec"], returncode=worker_rc, stdout="")

            with (
                mock.patch.object(swarm, "_repo_root", return_value=repo),
                mock.patch.object(swarm, "_find_task_file_anywhere", return_value=task_file),
                mock.patch.object(swarm, "load_task", return_value=task),
                mock.patch.object(swarm, "_codex_exec_cmd", return_value=["codex", "exec", "task"]),
                mock.patch.object(swarm, "_git_status_entries", return_value=[]),
                mock.patch.object(swarm, "_snapshot_untracked_ignored_fingerprints", return_value={}),
                mock.patch.object(swarm, "_update_task_status_and_notes", update_status_mock),
                mock.patch.object(swarm, "_git_has_changes", return_value=False),
                mock.patch.object(swarm, "_run", return_value=worker_cp),
                mock.patch("sys.stdout", new_callable=io.StringIO) as captured_stdout,
            ):
                rc = swarm.cmd_run_task(args)

            self.assertEqual(rc, 1)
            update_status_mock.assert_called_once()
            self.assertEqual(update_status_mock.call_args.kwargs["new_state"], "blocked")
            self.assertIn(
                f"worker_command_failed_rc={worker_rc}",
                update_status_mock.call_args.kwargs["note_line"],
            )

            payload = json.loads(captured_stdout.getvalue().strip())
            self.assertEqual(payload["state"], "blocked")
            self.assertEqual(payload["error"], "worker_command_failed")
            self.assertEqual(payload["reason"], f"worker_command_failed_rc={worker_rc}")
            self.assertEqual(payload["worker_returncode"], worker_rc)


if __name__ == "__main__":
    unittest.main()
