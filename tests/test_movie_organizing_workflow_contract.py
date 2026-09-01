import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "movie-organizing"
SCRIPT_PATH = SKILL_DIR / "scripts" / "movie_organizing_preprocessor.py"
ENTRY_SCRIPT = SKILL_DIR / "scripts" / "movie_organizing_task.py"
TASK_MODULE = SourceFileLoader(
    "movie_organizing_task_contract",
    str(ENTRY_SCRIPT),
).load_module()

preprocessor = SourceFileLoader(
    "movie_organizing_preprocessor_workflow_contract",
    str(SCRIPT_PATH),
).load_module()


FIXED_STEPS = (
    "verify_install",
    "scope_lock",
    "inventory",
    "naming_contract",
    "preprocess",
    "exception_resolution",
    "core_gate",
    "nfo_gate",
    "dedupe_gate",
    "cleanup_final_audit",
)


class MovieOrganizingWorkflowContractTest(unittest.TestCase):
    def _make(self, root: Path, relative: str, content: bytes = b"x") -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _make_action_required_units(self, root: Path, count: int = 25) -> None:
        director = root / "导演 Director"
        for index in range(count):
            movie_dir = director / f"中文片{index}.Movie{index}.2020"
            self._make(
                movie_dir,
                f"Movie{index}.2020.1080p.BluRay.x264-RLS.mkv",
            )

    def _make_rename_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        source_director = root / "导演 Director"
        source_dir = source_director / "影迷.The.Dot.Movie.2019"
        source_video = self._make(
            source_dir,
            "The.Dot.Movie.2019.1080p.BluRay.x264-RLS.mkv",
        )
        plan = preprocessor.make_plan(root)
        bundle = next(
            item
            for item in plan["bundles"]
            if Path(item["source_movie_dir"]).resolve() == source_dir.resolve()
        )
        target_dir = Path(bundle["expected_movie_dir_path"])
        target_video = Path(bundle["expected_video_target"])
        return source_video, target_dir, target_video

    def _write_slow_variant(self, root: Path, variant: str) -> tuple[dict, Path]:
        self._make_action_required_units(root, count=1)
        plan = preprocessor.make_plan(root)
        plan_path = Path(plan["plan_path"])
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
        if variant == "slow_channel":
            plan_data["slow_channel"] = True
        elif variant == "non_naming_kind":
            plan_data["plan_kind"] = "slow_channel"
        else:  # pragma: no cover - protects the test contract itself
            raise AssertionError(f"unknown plan variant: {variant}")
        plan_path.write_text(
            json.dumps(plan_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return plan_data, plan_path

    def _run_entry(self, mode: str, root: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
        self.assertTrue(
            ENTRY_SCRIPT.is_file(),
            "movie-organizing task entrypoint is required at scripts/movie_organizing_task.py",
        )
        process = subprocess.run(
            [sys.executable, str(ENTRY_SCRIPT), mode, "--task-root", str(root)],
            capture_output=True,
            text=True,
        )
        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - useful RED output
            self.fail(f"task entry did not emit JSON (rc={process.returncode}): {process.stderr}: {exc}")
        return process, payload

    def _write_recovery_record(
        self,
        root: Path,
        name: str,
        payload: dict,
        *,
        mtime_ns: int | None = None,
    ) -> Path:
        recovery = root / "_work-record_" / "recovery"
        recovery.mkdir(parents=True, exist_ok=True)
        path = recovery / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        if mtime_ns is not None:
            os.utime(path, ns=(mtime_ns, mtime_ns))
        return path

    def _assert_full_next_command(self, payload: dict, *expected: str) -> None:
        next_allowed = payload.get("next_allowed")
        self.assertIsInstance(next_allowed, dict)
        argv = next_allowed.get("argv")
        command = next_allowed.get("command")
        self.assertIsInstance(argv, list)
        self.assertTrue(argv)
        for token in expected:
            candidates = {str(token)}
            if isinstance(token, str) and "/" in token:
                candidates.add(str(Path(token).resolve()))
            self.assertTrue(candidates.intersection(argv), (token, argv))
        self.assertEqual(argv, shlex.split(command))

    def _audit_record(
        self,
        root: Path,
        name: str,
        *,
        completion_status: str,
        core_status: str = "PASS",
        dedupe_status: str = "PASS",
        cleanup_status: str = "PASS",
        candidate_groups: list | None = None,
        exceptions: list | None = None,
        action_required: list | None = None,
        core_counts: dict | None = None,
        plan_hash: str | None = None,
        pending_video_count: int | None = None,
        mtime_ns: int | None = None,
    ) -> Path:
        path = root / "_work-record_" / "recovery" / name
        payload = {
            "schema": "movie-organizing-audit/v1",
            "version": "1.3.6",
            "task_root": str(root.resolve()),
            "report_path": str(path),
            "status": "PASS" if completion_status != "BLOCKED" else "FAIL",
            "completion_status": completion_status,
            "core_gate": {
                "status": core_status,
                "exceptions": exceptions or [],
                "action_required": action_required or [],
                "counts": core_counts or {},
            },
            "dedupe_gate": {
                "status": dedupe_status,
                "candidate_groups": candidate_groups or [],
            },
            "cleanup_gate": {"status": cleanup_status},
        }
        if plan_hash is not None:
            payload["plan_hash"] = plan_hash
        if pending_video_count is not None:
            payload["pending_video_count"] = pending_video_count
        return self._write_recovery_record(root, name, payload, mtime_ns=mtime_ns)

    def _slow_record(
        self,
        root: Path,
        name: str,
        schema: str,
        payload: dict,
        *,
        mtime_ns: int | None = None,
    ) -> Path:
        base = {
            "schema": schema,
            "version": "1.3.6",
            "task_root": str(root.resolve()),
        }
        base.update(payload)
        return self._write_recovery_record(root, name, base, mtime_ns=mtime_ns)

    def test_plan_keeps_all_action_required_units_but_selects_at_most_twenty_for_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_action_required_units(root)

            plan = preprocessor.make_plan(root)
            summary = plan["summary"]
            bundles = plan["bundles"]
            selected = [item for item in bundles if item.get("selected_for_apply") is True]
            deferred = [item for item in bundles if item.get("selected_for_apply") is False]

            self.assertEqual(25, summary["action_required"])
            self.assertEqual(10, summary.get("selected_action_units"), summary)
            self.assertEqual(15, summary.get("deferred_action_units"), summary)
            self.assertEqual(10, len(selected))
            self.assertEqual(15, len(deferred))
            self.assertTrue(all(item["status"] == "ACTION_REQUIRED" for item in deferred))
            self.assertEqual(
                summary["planned_actions"],
                sum(
                    len(item.get("actions", []))
                    for item in selected
                ),
            )

    def test_mid_apply_failure_rolls_back_executed_actions_and_marks_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video, target_dir, target_video = self._make_rename_fixture(root)
            source_dir = source_video.parent
            plan = preprocessor.make_plan(root)
            rename_calls = 0
            original_rename = Path.rename

            def fail_on_second_rename(source, target):
                nonlocal rename_calls
                rename_calls += 1
                if rename_calls == 2:
                    raise OSError("injected mid-apply failure")
                return original_rename(source, target)

            with mock.patch.object(Path, "rename", new=fail_on_second_rename):
                result = preprocessor.apply_plan(plan, root=root)

            self.assertEqual("FAIL", result["status"])
            self.assertEqual("PASS", result.get("rollback_status"))
            self.assertGreaterEqual(result.get("executed_actions", 0), 1)
            self.assertGreaterEqual(result.get("rolled_back_actions", 0), 1)
            self.assertFalse(result.get("manual_recovery_required", True))
            self.assertTrue(source_dir.is_dir())
            self.assertTrue(source_video.is_file())
            self.assertFalse(target_dir.exists())
            self.assertFalse(target_video.exists())

    def test_post_verify_failure_rolls_back_all_executed_actions_and_marks_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video, target_dir, target_video = self._make_rename_fixture(root)
            source_dir = source_video.parent
            plan = preprocessor.make_plan(root)

            with mock.patch.object(
                preprocessor,
                "verify_plan",
                return_value={"status": "FAIL", "error_summary": "injected post-verify failure"},
            ):
                result = preprocessor.apply_plan(plan, root=root)

            self.assertEqual("FAIL", result["status"])
            self.assertEqual("PASS", result.get("rollback_status"))
            self.assertGreaterEqual(result.get("executed_actions", 0), 1)
            self.assertGreaterEqual(result.get("rolled_back_actions", 0), 1)
            self.assertFalse(result.get("manual_recovery_required", True))
            self.assertTrue(source_dir.is_dir())
            self.assertTrue(source_video.is_file())
            self.assertFalse(target_dir.exists())
            self.assertFalse(target_video.exists())

    def test_apply_plan_rejects_slow_channel_and_non_naming_plans_before_mutation(self):
        for variant in ("slow_channel", "non_naming_kind"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                plan, _plan_path = self._write_slow_variant(root, variant)
                source_video = next(root.rglob("*.mkv"))

                result = preprocessor.apply_plan(plan, root=root)

                self.assertEqual("FAIL", result["status"])
                self.assertEqual(0, result.get("executed_actions"))
                self.assertRegex(
                    result.get("error_summary", "").lower(),
                    r"slow|plan.?kind|naming",
                )
                self.assertTrue(source_video.exists())

    def test_cli_apply_rejects_slow_channel_and_non_naming_plans_before_mutation(self):
        for variant in ("slow_channel", "non_naming_kind"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _plan, plan_path = self._write_slow_variant(root, variant)
                source_video = next(root.rglob("*.mkv"))
                process = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT_PATH),
                        "apply",
                        "--task-root",
                        str(root),
                        "--plan",
                        str(plan_path),
                        "--dry-run",
                    ],
                    capture_output=True,
                    text=True,
                )
                result = json.loads(process.stdout)

                self.assertNotEqual(0, process.returncode)
                self.assertEqual("FAIL", result["status"])
                self.assertEqual(0, result.get("executed_actions"))
                self.assertRegex(
                    result.get("error_summary", "").lower(),
                    r"slow|plan.?kind|naming",
                )
                self.assertTrue(source_video.exists())

    def test_task_entry_repeats_complete_fixed_steps_and_one_next_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_action_required_units(root, count=1)

            with mock.patch.object(TASK_MODULE, "_prerequisites", return_value=(True, "")):
                first = TASK_MODULE.task_state(root, mode="start")
                second = TASK_MODULE.task_state(root, mode="start")
                status = TASK_MODULE.task_state(root, mode="status")

            for payload in (first, second, status):
                self.assertEqual(list(FIXED_STEPS), payload["steps"])
                self.assertIn(payload["phase"], FIXED_STEPS)
                next_allowed = payload["next_allowed"]
                self.assertTrue(next_allowed is None or isinstance(next_allowed, dict))
                if next_allowed is not None:
                    self.assertIsInstance(next_allowed.get("command"), str)
                    self.assertTrue(next_allowed["command"])
            self.assertEqual(first["steps"], second["steps"])
            self.assertEqual(first["steps"], status["steps"])
            self.assertEqual("inventory", first["phase"])
            self.assertEqual(["verify_install", "scope_lock", "naming_contract"], first["completed_steps"])
            self.assertIn("plan", first["next_allowed"]["argv"])

    def test_task_entry_stops_after_failed_apply_without_next_phase_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_action_required_units(root, count=1)
            self._run_entry("start", root)

            plan_output = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "plan", "--task-root", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            plan_path = json.loads(plan_output.stdout)["plan_path"]
            failed_apply = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "apply",
                    "--task-root",
                    str(root),
                    "--plan",
                    plan_path,
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, failed_apply.returncode)
            self.assertEqual("FAIL", json.loads(failed_apply.stdout)["status"])

            process, payload = self._run_entry("status", root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("STOP_RECOVERY_REQUIRED", payload["phase"])
            self.assertIsNone(payload["next_allowed"])

    def test_task_entry_formal_apply_pass_stays_in_preprocess_until_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_action_required_units(root, count=1)
            plan_output = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "plan", "--task-root", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            plan_path = json.loads(plan_output.stdout)["plan_path"]
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "apply",
                    "--task-root",
                    str(root),
                    "--plan",
                    plan_path,
                    "--dry-run",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "apply", "--task-root", str(root), "--plan", plan_path],
                check=True,
                capture_output=True,
                text=True,
            )

            process, payload = self._run_entry("status", root)

            self.assertEqual(0, process.returncode)
            self.assertEqual("preprocess", payload["phase"])
            self.assertIn("verify", payload["next_allowed"]["argv"])
            self.assertIn(payload["phase"], FIXED_STEPS)

    def test_task_entry_uses_latest_plan_chain_instead_of_stale_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recovery = root / "_work-record_" / "recovery"
            recovery.mkdir(parents=True)
            base = {
                "schema": "movie-organizing-preprocessor/result/v1",
                "version": "1.3.4",
                "mode": "apply",
                "dry_run": False,
                "task_root": str(root.resolve()),
                "error_summary": "",
            }
            stale_failure = {
                **base,
                "plan_hash": "old-plan",
                "status": "FAIL",
                "rollback_status": "PASS",
                "manual_recovery_required": False,
                "error_summary": "stale plan failed",
            }
            current_pass = {
                **base,
                "plan_hash": "new-plan",
                "status": "PASS",
            }
            stale_path = recovery / "result-apply-old.json"
            current_path = recovery / "result-apply-new.json"
            stale_path.write_text(json.dumps(stale_failure), encoding="utf-8")
            current_path.write_text(json.dumps(current_pass), encoding="utf-8")
            os.utime(stale_path, ns=(1_000_000_000, 1_000_000_000))
            os.utime(current_path, ns=(2_000_000_000, 2_000_000_000))

            process, payload = self._run_entry("status", root)

            self.assertEqual(0, process.returncode)
            self.assertNotEqual("STOP_RECOVERY_REQUIRED", payload["phase"])
            self.assertEqual("preprocess", payload["phase"])
            self.assertIn("verify", payload["next_allowed"]["argv"])

    def test_task_entry_initial_next_action_is_a_complete_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(TASK_MODULE, "_prerequisites", return_value=(True, "")):
                payload = TASK_MODULE.task_state(root, mode="start")

            self.assertEqual("1.3.6", payload["version"])
            self.assertEqual("inventory", payload["phase"])
            self._assert_full_next_command(payload, "plan", "--task-root", str(root.resolve()))

    def test_task_entry_stops_when_read_only_prerequisites_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(TASK_MODULE, "_prerequisites", return_value=(False, "manifest mismatch")):
                payload = TASK_MODULE.task_state(root, mode="start")

            self.assertEqual("FAIL", payload["status"])
            self.assertEqual("STOP_RECOVERY_REQUIRED", payload["phase"])
            self.assertIsNone(payload["next_allowed"])
            self.assertIn("manifest mismatch", payload["error"])

    def test_task_entry_rejects_a_symlink_task_root_before_canonicalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            actual = parent / "actual"
            actual.mkdir()
            link = parent / "task-link"
            link.symlink_to(actual, target_is_directory=True)

            payload = TASK_MODULE.task_state(link, mode="status")

            self.assertEqual("FAIL", payload["status"])
            self.assertEqual("STOP_RECOVERY_REQUIRED", payload["phase"])
            self.assertIsNone(payload["next_allowed"])
            self.assertIn("real directory", payload["error"])

    def test_task_entry_cli_status_returns_nonzero_for_stop_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            process, payload = self._run_entry("status", missing)

            self.assertEqual("FAIL", payload["status"])
            self.assertEqual("STOP_RECOVERY_REQUIRED", payload["phase"])
            self.assertNotEqual(0, process.returncode)

    def test_task_entry_advances_past_prerequisites_without_external_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(TASK_MODULE, "_prerequisites", return_value=(True, "")):
                payload = TASK_MODULE.task_state(root, mode="status")

            self.assertEqual("inventory", payload["phase"])
            self.assertEqual(["verify_install", "scope_lock", "naming_contract"], payload["completed_steps"])
            self._assert_full_next_command(payload, "plan", "--task-root", str(root.resolve()))

    def test_task_entry_walks_naming_plan_dry_run_formal_verify_with_full_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = self._write_recovery_record(
                root,
                "plan-naming.json",
                {
                    "schema": "movie-organizing-preprocessor/v1",
                    "version": "1.3.6",
                    "plan_kind": "naming",
                    "task_root": str(root.resolve()),
                    "plan_hash": "naming-plan",
                    "summary": {"deferred_action_units": 0},
                },
                mtime_ns=1_000,
            )
            process, payload = self._run_entry("status", root)
            self.assertEqual(0, process.returncode)
            self.assertEqual("preprocess", payload["phase"])
            self._assert_full_next_command(
                payload,
                "apply",
                "--task-root",
                str(root.resolve()),
                "--plan",
                str(plan_path.resolve()),
                "--dry-run",
            )

            self._write_recovery_record(
                root,
                "result-apply-dry.json",
                {
                    "schema": "movie-organizing-preprocessor/result/v1",
                    "version": "1.3.6",
                    "mode": "apply",
                    "dry_run": True,
                    "status": "PASS",
                    "task_root": str(root.resolve()),
                    "plan_hash": "naming-plan",
                },
                mtime_ns=2_000,
            )
            _process, payload = self._run_entry("status", root)
            self.assertEqual("preprocess", payload["phase"])
            self._assert_full_next_command(
                payload,
                "apply",
                "--task-root",
                str(root.resolve()),
                "--plan",
                str(plan_path.resolve()),
            )

            self._write_recovery_record(
                root,
                "result-apply-formal.json",
                {
                    "schema": "movie-organizing-preprocessor/result/v1",
                    "version": "1.3.6",
                    "mode": "apply",
                    "dry_run": False,
                    "status": "PASS",
                    "task_root": str(root.resolve()),
                    "plan_hash": "naming-plan",
                },
                mtime_ns=3_000,
            )
            _process, payload = self._run_entry("status", root)
            self.assertEqual("preprocess", payload["phase"])
            self._assert_full_next_command(payload, "verify", "--task-root", str(root.resolve()))

            self._write_recovery_record(
                root,
                "result-verify.json",
                {
                    "schema": "movie-organizing-preprocessor/result/v1",
                    "version": "1.3.6",
                    "mode": "verify",
                    "status": "PASS",
                    "task_root": str(root.resolve()),
                    "plan_hash": "naming-plan",
                },
                mtime_ns=4_000,
            )
            _process, payload = self._run_entry("status", root)
            self.assertEqual("core_gate", payload["phase"])
            self._assert_full_next_command(payload, "audit", "--task-root", str(root.resolve()))

    def test_task_entry_requires_fresh_plan_when_naming_batch_is_deferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_recovery_record(
                root,
                "plan-batch.json",
                {
                    "schema": "movie-organizing-preprocessor/v1",
                    "version": "1.3.6",
                    "plan_kind": "naming",
                    "task_root": str(root.resolve()),
                    "plan_hash": "batch-plan",
                    "summary": {"deferred_action_units": 3},
                },
                mtime_ns=1_000,
            )
            self._write_recovery_record(
                root,
                "result-verify-batch.json",
                {
                    "schema": "movie-organizing-preprocessor/result/v1",
                    "version": "1.3.6",
                    "mode": "verify",
                    "status": "PASS",
                    "task_root": str(root.resolve()),
                    "plan_hash": "batch-plan",
                },
                mtime_ns=2_000,
            )
            _process, payload = self._run_entry("status", root)
            self.assertEqual("preprocess", payload["phase"])
            self._assert_full_next_command(payload, "plan", "--task-root", str(root.resolve()))

    def test_audit_fresh_plan_anchor_supersedes_old_naming_verify_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_recovery_record(
                root,
                "plan-old.json",
                {
                    "schema": "movie-organizing-preprocessor/v1",
                    "version": "1.3.6",
                    "plan_kind": "naming",
                    "task_root": str(root.resolve()),
                    "plan_hash": "same-plan",
                    "summary": {"deferred_action_units": 0},
                },
                mtime_ns=1_000,
            )
            self._write_recovery_record(
                root,
                "result-verify-old.json",
                {
                    "schema": "movie-organizing-preprocessor/result/v1",
                    "version": "1.3.6",
                    "mode": "verify",
                    "status": "PASS",
                    "task_root": str(root.resolve()),
                    "plan_hash": "same-plan",
                },
                mtime_ns=2_000,
            )
            self._write_recovery_record(
                root,
                "plan-fresh-from-audit.json",
                {
                    "schema": "movie-organizing-preprocessor/v1",
                    "version": "1.3.6",
                    "plan_kind": "naming",
                    "task_root": str(root.resolve()),
                    "plan_hash": "same-plan",
                    "summary": {"deferred_action_units": 0},
                },
                mtime_ns=3_000,
            )
            audit = self._audit_record(
                root,
                "audit-after-fresh-plan.json",
                completion_status="BLOCKED",
                core_status="FAIL",
                exceptions=[{"path": str(root / "movie"), "reason": "ambiguous"}],
                plan_hash="same-plan",
                mtime_ns=4_000,
            )

            _process, payload = self._run_entry("status", root)

            self.assertEqual("exception_resolution", payload["phase"])
            self._assert_full_next_command(
                payload,
                "template",
                "--task-root",
                str(root.resolve()),
                "--audit",
                str(audit.resolve()),
                "--phase",
                "core_exception",
            )

    def test_task_entry_routes_core_blocked_audit_to_bounded_slowpath_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = self._audit_record(
                root,
                "audit-core-blocked.json",
                completion_status="BLOCKED",
                core_status="FAIL",
                exceptions=[{"path": str(root / "法国 Director"), "reason": "ambiguous"}],
                mtime_ns=1_000,
            )
            _process, payload = self._run_entry("status", root)
            self.assertEqual("exception_resolution", payload["phase"])
            self._assert_full_next_command(
                payload,
                "template",
                "--task-root",
                str(root.resolve()),
                "--audit",
                str(audit),
                "--phase",
                "core_exception",
            )

    def test_task_entry_routes_core_pass_dedupe_candidates_to_dedupe_slowpath(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = self._audit_record(
                root,
                "audit-dedupe-blocked.json",
                completion_status="BLOCKED",
                core_status="PASS",
                dedupe_status="FAIL",
                candidate_groups=[{"group_id": "g1", "members": [str(root / "a"), str(root / "b")]}],
                mtime_ns=1_000,
            )
            _process, payload = self._run_entry("status", root)
            self.assertEqual("dedupe_gate", payload["phase"])
            self._assert_full_next_command(
                payload,
                "template",
                "--task-root",
                str(root.resolve()),
                "--audit",
                str(audit),
                "--phase",
                "dedupe",
            )

    def test_task_entry_recognizes_slowpath_template_plan_and_apply_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = self._audit_record(
                root,
                "audit-core.json",
                completion_status="BLOCKED",
                core_status="FAIL",
                mtime_ns=1_000,
            )
            template = self._slow_record(
                root,
                "slow-template-core.json",
                "movie-organizing-slowpath/template/v1",
                {
                    "phase": "core_exception",
                    "template_path": str(root / "_work-record_" / "recovery" / "slow-template-core.json"),
                    "audit_path": str(audit),
                    "items": [],
                },
                mtime_ns=2_000,
            )
            decisions = self._slow_record(
                root,
                "decisions-core.json",
                "movie-organizing-slowpath/decisions/v1",
                {
                    "phase": "core_exception",
                    "items": [],
                },
                mtime_ns=3_000,
            )
            _process, payload = self._run_entry("status", root)
            self.assertEqual("exception_resolution", payload["phase"])
            self._assert_full_next_command(
                payload,
                "plan",
                "--task-root",
                str(root.resolve()),
                "--audit",
                str(audit),
                "--template",
                str(template),
                "--decisions",
                str(decisions),
            )

            plan = self._slow_record(
                root,
                "slow-plan-core.json",
                "movie-organizing-slowpath/plan/v1",
                {
                    "phase": "core_exception",
                    "plan_path": str(root / "_work-record_" / "recovery" / "slow-plan-core.json"),
                    "plan_hash": "slow-plan",
                    "actions": [],
                },
                mtime_ns=4_000,
            )
            _process, payload = self._run_entry("status", root)
            self.assertEqual("exception_resolution", payload["phase"])
            self._assert_full_next_command(
                payload,
                "apply",
                "--task-root",
                str(root.resolve()),
                "--plan",
                str(plan),
                "--dry-run",
            )

            self._slow_record(
                root,
                "slow-result-dry.json",
                "movie-organizing-slowpath/result/v1",
                {
                    "mode": "apply",
                    "dry_run": True,
                    "status": "PASS",
                    "plan_hash": "slow-plan",
                },
                mtime_ns=5_000,
            )
            # A slowpath runner may emit a fresh audit while preparing the
            # next command.  The active plan's dry-run result still owns the
            # chain and must authorize formal apply, not another template.
            self._audit_record(
                root,
                "audit-emitted-by-slowpath.json",
                completion_status="BLOCKED",
                core_status="FAIL",
                mtime_ns=5_500,
            )
            _process, payload = self._run_entry("status", root)
            self._assert_full_next_command(
                payload,
                "apply",
                "--task-root",
                str(root.resolve()),
                "--plan",
                str(plan),
            )

            self._slow_record(
                root,
                "slow-result-formal.json",
                "movie-organizing-slowpath/result/v1",
                {
                    "mode": "apply",
                    "dry_run": False,
                    "status": "PASS",
                    "plan_hash": "slow-plan",
                },
                mtime_ns=6_000,
            )
            _process, payload = self._run_entry("status", root)
            self._assert_full_next_command(
                payload,
                "verify",
                "--task-root",
                str(root.resolve()),
                "--plan",
                str(plan),
            )

            self._slow_record(
                root,
                "slow-result-verify.json",
                "movie-organizing-slowpath/result/v1",
                {
                    "mode": "verify",
                    "status": "PASS",
                    "plan_hash": "slow-plan",
                },
                mtime_ns=7_000,
            )
            _process, payload = self._run_entry("status", root)
            self.assertEqual("core_gate", payload["phase"])
            self._assert_full_next_command(payload, "audit", "--task-root", str(root.resolve()))

    def test_newer_slowpath_template_supersedes_completed_naming_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_recovery_record(
                root,
                "plan-naming.json",
                {
                    "schema": "movie-organizing-preprocessor/v1",
                    "version": "1.3.6",
                    "plan_kind": "naming",
                    "task_root": str(root.resolve()),
                    "plan_hash": "naming-plan",
                    "summary": {"deferred_action_units": 0},
                },
                mtime_ns=1_000,
            )
            self._write_recovery_record(
                root,
                "result-verify-naming.json",
                {
                    "schema": "movie-organizing-preprocessor/result/v1",
                    "version": "1.3.6",
                    "mode": "verify",
                    "status": "PASS",
                    "task_root": str(root.resolve()),
                    "plan_hash": "naming-plan",
                },
                mtime_ns=2_000,
            )
            audit = self._audit_record(
                root,
                "audit-core-blocked.json",
                completion_status="BLOCKED",
                core_status="FAIL",
                mtime_ns=3_000,
            )
            self._slow_record(
                root,
                "slow-template-core.json",
                "movie-organizing-slowpath/template/v1",
                {
                    "phase": "core_exception",
                    "template_path": str(root / "_work-record_" / "recovery" / "slow-template-core.json"),
                    "audit_path": str(audit),
                    "items": [],
                },
                mtime_ns=4_000,
            )

            _process, payload = self._run_entry("status", root)

            self.assertEqual("exception_resolution", payload["phase"])
            self.assertIsNone(payload["next_allowed"])
            self.assertIn("semantic decisions", payload["error"])

    def test_task_entry_treats_core_pending_and_complete_as_terminal_audit_states(self):
        for completion_status in ("CORE_COMPLETE_PENDING", "COMPLETE"):
            with self.subTest(completion_status=completion_status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._audit_record(
                    root,
                    f"audit-{completion_status}.json",
                    completion_status=completion_status,
                    mtime_ns=1_000,
                )
                _process, payload = self._run_entry("status", root)
                self.assertEqual("cleanup_final_audit", payload["phase"])
                self.assertIsNone(payload["next_allowed"])

    def test_task_entry_allows_fresh_plan_after_complete_rollback_but_stops_manual_recovery(self):
        for rollback_status, manual, should_stop in (
            ("PASS", False, False),
            ("FAIL", True, True),
            ("PASS", True, True),
        ):
            with self.subTest(rollback_status=rollback_status, manual=manual), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._write_recovery_record(
                    root,
                    "plan-current.json",
                    {
                        "schema": "movie-organizing-preprocessor/v1",
                        "version": "1.3.6",
                        "plan_kind": "naming",
                        "task_root": str(root.resolve()),
                        "plan_hash": "current-plan",
                        "summary": {"deferred_action_units": 0},
                    },
                    mtime_ns=1_000,
                )
                self._write_recovery_record(
                    root,
                    "result-current-fail.json",
                    {
                        "schema": "movie-organizing-preprocessor/result/v1",
                        "version": "1.3.6",
                        "mode": "apply",
                        "dry_run": False,
                        "status": "FAIL",
                        "task_root": str(root.resolve()),
                        "plan_hash": "current-plan",
                        "rollback_status": rollback_status,
                        "manual_recovery_required": manual,
                    },
                    mtime_ns=2_000,
                )
                _process, payload = self._run_entry("status", root)
                if should_stop:
                    self.assertEqual("STOP_RECOVERY_REQUIRED", payload["phase"])
                    self.assertIsNone(payload["next_allowed"])
                else:
                    self.assertEqual("preprocess", payload["phase"])
                    self._assert_full_next_command(payload, "plan", "--task-root", str(root.resolve()))

    def test_task_entry_applies_the_same_recovery_gate_to_formal_verify_failures(self):
        for rollback_status, manual, should_stop in (("PASS", False, False), ("FAIL", False, True)):
            with self.subTest(rollback_status=rollback_status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._write_recovery_record(
                    root,
                    "result-verify-fail.json",
                    {
                        "schema": "movie-organizing-preprocessor/result/v1",
                        "version": "1.3.6",
                        "mode": "verify",
                        "status": "FAIL",
                        "task_root": str(root.resolve()),
                        "plan_hash": "verify-plan",
                        "rollback_status": rollback_status,
                        "manual_recovery_required": manual,
                    },
                    mtime_ns=1_000,
                )
                _process, payload = self._run_entry("status", root)
                if should_stop:
                    self.assertEqual("STOP_RECOVERY_REQUIRED", payload["phase"])
                    self.assertIsNone(payload["next_allowed"])
                else:
                    self.assertEqual("preprocess", payload["phase"])
                    self._assert_full_next_command(payload, "plan", "--task-root", str(root.resolve()))

    def test_manual_recovery_failure_cannot_be_masked_by_newer_plan_or_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_recovery_record(
                root,
                "result-manual-fail.json",
                {
                    "schema": "movie-organizing-preprocessor/result/v1",
                    "version": "1.3.6",
                    "mode": "apply",
                    "dry_run": False,
                    "status": "FAIL",
                    "task_root": str(root.resolve()),
                    "plan_hash": "failed-plan",
                    "rollback_status": "FAIL",
                    "manual_recovery_required": True,
                    "error_summary": "rollback could not restore source",
                },
                mtime_ns=1_000,
            )
            self._write_recovery_record(
                root,
                "plan-newer.json",
                {
                    "schema": "movie-organizing-preprocessor/v1",
                    "version": "1.3.6",
                    "plan_kind": "naming",
                    "task_root": str(root.resolve()),
                    "plan_hash": "new-plan",
                    "summary": {"deferred_action_units": 0},
                },
                mtime_ns=2_000,
            )
            self._audit_record(
                root,
                "audit-newer.json",
                completion_status="COMPLETE",
                mtime_ns=3_000,
            )

            _process, payload = self._run_entry("status", root)

            self.assertEqual("FAIL", payload["status"])
            self.assertEqual("STOP_RECOVERY_REQUIRED", payload["phase"])
            self.assertIsNone(payload["next_allowed"])
            self.assertIn("rollback", payload["error"])

    def test_audit_naming_backlog_returns_to_preprocess_and_does_not_claim_preprocess_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._audit_record(
                root,
                "audit-naming-backlog.json",
                completion_status="BLOCKED",
                core_status="FAIL",
                action_required=[{"path": str(root / "movie"), "reason": "rename required"}],
                core_counts={"required_actions_remaining": 1},
                mtime_ns=1_000,
            )

            _process, payload = self._run_entry("status", root)

            self.assertEqual("preprocess", payload["phase"])
            self.assertNotIn("preprocess", payload["completed_steps"])
            self._assert_full_next_command(payload, "plan", "--task-root", str(root.resolve()))

    def test_pending_only_audit_stops_without_empty_slowpath_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._audit_record(
                root,
                "audit-pending-only.json",
                completion_status="BLOCKED",
                core_status="FAIL",
                core_counts={"active_video_units": 0},
                pending_video_count=2,
                mtime_ns=1_000,
            )

            process, payload = self._run_entry("status", root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertEqual("STOP_PENDING_CONFIRMATION", payload["phase"])
            self.assertIsNone(payload["next_allowed"])
            self.assertIn("待确认 2 项", payload["error"])
            self.assertIn("BLOCKED", payload["error"])
            self.assertNotIn("template", payload.get("error", "").lower())
            self.assertNotIn("awaiting decisions", payload.get("error", "").lower())

    def test_official_pending_only_does_not_claim_core_complete_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._audit_record(
                root,
                "audit-official-pending-only.json",
                completion_status="CORE_COMPLETE_PENDING",
                core_status="PASS",
                core_counts={"active_video_units": 0},
                pending_video_count=1,
                mtime_ns=1_000,
            )

            process, payload = self._run_entry("status", root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertEqual("STOP_PENDING_CONFIRMATION", payload["phase"])
            self.assertIsNone(payload["next_allowed"])
            self.assertIn("待确认 1 项", payload["error"])
            self.assertNotEqual("cleanup_final_audit", payload["phase"])

    def test_empty_audit_stops_recovery_without_empty_slowpath_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._audit_record(
                root,
                "audit-empty.json",
                completion_status="BLOCKED",
                core_status="FAIL",
                core_counts={"active_video_units": 0},
                pending_video_count=0,
                mtime_ns=1_000,
            )

            process, payload = self._run_entry("status", root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertEqual("STOP_RECOVERY_REQUIRED", payload["phase"])
            self.assertIsNone(payload["next_allowed"])
            self.assertNotIn("template", payload.get("error", "").lower())
            self.assertNotIn("awaiting decisions", payload.get("error", "").lower())

    def test_active_exception_still_enters_slowpath_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = self._audit_record(
                root,
                "audit-active-exception.json",
                completion_status="BLOCKED",
                core_status="FAIL",
                exceptions=[{"path": str(root / "movie"), "reason": "ambiguous"}],
                core_counts={"active_video_units": 1, "active_exception_units": 1},
                pending_video_count=0,
                mtime_ns=1_000,
            )

            process, payload = self._run_entry("status", root)

            self.assertEqual(0, process.returncode)
            self.assertEqual("exception_resolution", payload["phase"])
            self._assert_full_next_command(
                payload,
                "template",
                "--task-root",
                str(root.resolve()),
                "--audit",
                str(audit.resolve()),
                "--phase",
                "core_exception",
            )

    def test_active_movie_with_pending_keeps_core_complete_pending_terminal_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._audit_record(
                root,
                "audit-active-and-pending.json",
                completion_status="CORE_COMPLETE_PENDING",
                core_status="PASS",
                core_counts={"active_video_units": 1},
                pending_video_count=1,
                mtime_ns=1_000,
            )

            process, payload = self._run_entry("status", root)

            self.assertEqual(0, process.returncode)
            self.assertEqual("cleanup_final_audit", payload["phase"])
            self.assertIsNone(payload["next_allowed"])


if __name__ == "__main__":
    unittest.main()
