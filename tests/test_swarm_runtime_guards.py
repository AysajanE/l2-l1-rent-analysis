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
    def test_path_is_allowed_allows_ephemeral_runtime_paths(self) -> None:
        ok, reason = swarm._path_is_allowed(
            path="src/etl/__pycache__/growthepie_fetch.cpython-311.pyc",
            allowed_paths=["src/etl/"],
            disallowed_paths=[],
            task_file_paths=set(),
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_codex_review_cmd_uses_uncommitted_without_base(self) -> None:
        with mock.patch.object(swarm, "_which_or_none", return_value="/usr/bin/codex"):
            cmd = swarm._codex_review_cmd(prompt="review", unattended=True, workdir=Path("."))
        self.assertIn("review", cmd)
        self.assertIn("--uncommitted", cmd)
        self.assertNotIn("--base", cmd)

    def test_runtime_side_effect_prefixes_infer_raw_from_manifest_allowlist(self) -> None:
        prefixes = swarm._runtime_side_effect_prefixes_from_allowed_paths(
            [
                "data/raw_manifest/bq_ethereum_rollup_costs_",
                "data/processed/onchain/",
            ]
        )
        self.assertIn("data/raw/bq_ethereum_rollup_costs/", prefixes)
        self.assertIn("data/processed/onchain/", prefixes)

    def test_is_allowed_runtime_side_effect_respects_inferred_prefixes(self) -> None:
        prefixes = {
            "data/raw/bq_ethereum_rollup_costs/",
            "data/processed/onchain/",
        }
        self.assertTrue(
            swarm._is_allowed_runtime_side_effect(
                path="data/raw/",
                runtime_prefixes=prefixes,
            )
        )
        self.assertTrue(
            swarm._is_allowed_runtime_side_effect(
                path="data/processed/",
                runtime_prefixes=prefixes,
            )
        )
        self.assertTrue(
            swarm._is_allowed_runtime_side_effect(
                path="data/raw/bq_ethereum_rollup_costs/2026-02-06-r2/",
                runtime_prefixes=prefixes,
            )
        )
        self.assertTrue(
            swarm._is_allowed_runtime_side_effect(
                path="data/processed/onchain/",
                runtime_prefixes=prefixes,
            )
        )
        self.assertFalse(
            swarm._is_allowed_runtime_side_effect(
                path="data/raw/other_source/",
                runtime_prefixes=prefixes,
            )
        )

    def test_snapshot_untracked_ignored_fingerprints_expands_runtime_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            leaf = root / "data" / "raw" / "bq_ethereum_rollup_costs" / "2026-02-06"
            leaf.mkdir(parents=True, exist_ok=True)
            (leaf / "query.sql").write_text("select 1;\n", encoding="utf-8")

            entries = [{"xy": "!!", "path": "data/raw/", "old_path": ""}]
            snap = swarm._snapshot_untracked_ignored_fingerprints(
                cwd=root,
                status_entries=entries,
                skip_prefixes=(),
            )

            self.assertIn("data/raw/bq_ethereum_rollup_costs/", snap)
            self.assertNotIn("data/raw/", snap)

    def test_classify_quality_gate_failure_out_of_scope_as_warning(self) -> None:
        failures = swarm._parse_quality_gate_failures(
            "[processed_manifest_consistency] ok=False details={'failures': "
            "['data/processed_manifest/example_2026-02-06.json:outputs[0]:missing_output_file:"
            "data/processed/panels/daily_rollup_panel_v1_sample.csv']}"
        )
        blocking, warnings = swarm._classify_quality_gate_failures(
            failures=failures,
            allowed_paths=["src/etl/", "data/raw_manifest/"],
            disallowed_paths=[],
            task_file_paths={".orchestrator/backlog/T999_guard.md"},
        )
        self.assertEqual(blocking, [])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["gate"], "processed_manifest_consistency")

    def test_classify_quality_gate_failure_in_scope_blocks(self) -> None:
        failures = swarm._parse_quality_gate_failures(
            "[raw_manifest_validity] ok=False details={'failures': "
            "['data/raw_manifest/growthepie_2026-02-06.json:missing_keys:transform']}"
        )
        blocking, warnings = swarm._classify_quality_gate_failures(
            failures=failures,
            allowed_paths=["src/etl/", "data/raw_manifest/"],
            disallowed_paths=[],
            task_file_paths={".orchestrator/backlog/T999_guard.md"},
        )
        self.assertEqual(warnings, [])
        self.assertEqual(len(blocking), 1)
        self.assertEqual(blocking[0]["reason"], "quality_gate_failure_in_scope")

    def test_classify_quality_gate_failure_critical_gate_always_blocks(self) -> None:
        failures = swarm._parse_quality_gate_failures(
            "[protocol_complete] ok=False details={'failures': ['docs/protocol.md:todo_stub']}"
        )
        blocking, warnings = swarm._classify_quality_gate_failures(
            failures=failures,
            allowed_paths=["src/etl/"],
            disallowed_paths=[],
            task_file_paths={".orchestrator/backlog/T999_guard.md"},
        )
        self.assertEqual(warnings, [])
        self.assertEqual(len(blocking), 1)
        self.assertEqual(blocking[0]["reason"], "critical_quality_gate")

    def test_compute_workstream_locks_ignores_non_active_claimed_tasks(self) -> None:
        repo = Path("/tmp/repo")

        def _task(task_id: str, workstream: str, state: str, parallel_ok: bool) -> swarm.Task:
            return swarm.Task(
                path=Path(f".orchestrator/backlog/{task_id}.md"),
                task_id=task_id,
                title=task_id,
                workstream=workstream,
                role="Worker",
                priority="medium",
                dependencies=[],
                parallel_ok=parallel_ok,
                allowed_paths=[],
                disallowed_paths=[],
                outputs=[],
                gates=[],
                stop_conditions=[],
                required_env=[],
                state=state,
                last_updated=None,
            )

        tasks_by_id = {
            "T900": _task("T900", "W1", "backlog", parallel_ok=False),
            "T901": _task("T901", "W1", "blocked", parallel_ok=False),
            "T902": _task("T902", "W2", "active", parallel_ok=False),
            "T903": _task("T903", "W3", "active", parallel_ok=True),
        }

        with (
            mock.patch.object(swarm, "_find_task_file_anywhere", side_effect=lambda tid, _repo: tasks_by_id[tid].path),
            mock.patch.object(swarm, "load_task", side_effect=lambda path: tasks_by_id[path.stem]),
        ):
            locked, parallel_only = swarm._compute_workstream_locks(repo=repo, claimed_ids=set(tasks_by_id.keys()))

        self.assertEqual(locked, {"W2"})
        self.assertEqual(parallel_only, {"W3"})

    def test_run_task_treats_out_of_scope_quality_gate_failure_as_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            task_file = repo / ".orchestrator" / "active" / "T998_scope.md"
            task_file.parent.mkdir(parents=True, exist_ok=True)
            task_file.write_text("placeholder\n", encoding="utf-8")

            task = swarm.Task(
                path=task_file,
                task_id="T998",
                title="scope-warning-test",
                workstream="W0",
                role="worker",
                priority="high",
                dependencies=[],
                parallel_ok=False,
                allowed_paths=["src/etl/", "data/raw_manifest/"],
                disallowed_paths=[],
                outputs=[],
                gates=["make gate"],
                stop_conditions=[],
                required_env=[],
                state="active",
                last_updated=None,
            )

            args = argparse.Namespace(
                unattended=False,
                task_id="T998",
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

            worker_cp = subprocess.CompletedProcess(args=["codex", "exec"], returncode=0, stdout="")
            review_cp = subprocess.CompletedProcess(args=["codex", "review"], returncode=0, stdout="ok\n")
            gate_cp = subprocess.CompletedProcess(
                args=["make gate"],
                returncode=2,
                stdout=(
                    "[processed_manifest_consistency] ok=False details={'count': 1, 'checked_outputs': 0, "
                    "'failures': ['data/processed_manifest/example_2026-02-06.json:outputs[0]:missing_output_file:"
                    "data/processed/panels/daily_rollup_panel_v1_sample.csv']}\n"
                ),
            )

            update_status_mock = mock.Mock()
            run_side_effect = [worker_cp, review_cp]

            with (
                mock.patch.object(swarm, "_repo_root", return_value=repo),
                mock.patch.object(swarm, "_find_task_file_anywhere", return_value=task_file),
                mock.patch.object(swarm, "load_task", return_value=task),
                mock.patch.object(swarm, "_codex_exec_cmd", return_value=["codex", "exec", "task"]),
                mock.patch.object(swarm, "_git_status_entries", return_value=[]),
                mock.patch.object(swarm, "_snapshot_untracked_ignored_fingerprints", return_value={}),
                mock.patch.object(swarm, "_update_task_status_and_notes", update_status_mock),
                mock.patch.object(swarm, "_git_has_changes", return_value=False),
                mock.patch.object(swarm, "_git_current_branch", return_value="T998_scope"),
                mock.patch.object(swarm, "_run", side_effect=run_side_effect),
                mock.patch("subprocess.run", return_value=gate_cp),
                mock.patch("sys.stdout", new_callable=io.StringIO) as captured_stdout,
            ):
                rc = swarm.cmd_run_task(args)

            self.assertEqual(rc, 0)
            update_status_mock.assert_called_once()
            self.assertEqual(update_status_mock.call_args.kwargs["new_state"], "ready_for_review")
            self.assertIn(
                "Non-blocking out-of-scope gate warnings",
                update_status_mock.call_args.kwargs["note_line"],
            )

            raw = captured_stdout.getvalue().strip()
            payload = json.loads(raw[raw.find("{") :])
            self.assertEqual(payload["state"], "ready_for_review")
            self.assertTrue(payload["gate_ok"])
            self.assertEqual(payload["gate_blocking_failures"], [])
            self.assertEqual(len(payload["gate_warning_failures"]), 1)

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

    def test_run_task_allows_scoped_runtime_side_effect_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            task_file = repo / ".orchestrator" / "active" / "T997_runtime.md"
            task_file.parent.mkdir(parents=True, exist_ok=True)
            task_file.write_text("placeholder\n", encoding="utf-8")

            task = swarm.Task(
                path=task_file,
                task_id="T997",
                title="runtime-side-effect-test",
                workstream="W2",
                role="worker",
                priority="high",
                dependencies=[],
                parallel_ok=False,
                allowed_paths=[
                    "src/etl/l1_rollup_costs_bigquery.py",
                    "data/raw_manifest/bq_ethereum_rollup_costs_",
                    "data/processed/onchain/",
                ],
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
                task_id="T997",
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

            worker_cp = subprocess.CompletedProcess(args=["codex", "exec"], returncode=0, stdout="")
            review_cp = subprocess.CompletedProcess(args=["codex", "review"], returncode=0, stdout="ok\n")

            update_status_mock = mock.Mock()
            with (
                mock.patch.object(swarm, "_repo_root", return_value=repo),
                mock.patch.object(swarm, "_find_task_file_anywhere", return_value=task_file),
                mock.patch.object(swarm, "load_task", return_value=task),
                mock.patch.object(swarm, "_codex_exec_cmd", return_value=["codex", "exec", "task"]),
                mock.patch.object(swarm, "_git_status_entries", return_value=[]),
                mock.patch.object(swarm, "_snapshot_untracked_ignored_fingerprints", return_value={}),
                mock.patch.object(swarm, "_collect_changed_paths", return_value=([], ["data/raw/", "data/raw/bq_ethereum_rollup_costs/", "data/processed/onchain/"])),
                mock.patch.object(swarm, "_update_task_status_and_notes", update_status_mock),
                mock.patch.object(swarm, "_git_has_changes", return_value=False),
                mock.patch.object(swarm, "_git_current_branch", return_value="T997_runtime"),
                mock.patch.object(swarm, "_run", side_effect=[worker_cp, review_cp]),
                mock.patch("sys.stdout", new_callable=io.StringIO) as captured_stdout,
            ):
                rc = swarm.cmd_run_task(args)

            self.assertEqual(rc, 0)
            update_status_mock.assert_called_once()
            self.assertEqual(update_status_mock.call_args.kwargs["new_state"], "ready_for_review")

            payload = json.loads(captured_stdout.getvalue().strip())
            self.assertTrue(payload["ownership_ok"])
            self.assertEqual(payload["ownership_failures"], [])

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
