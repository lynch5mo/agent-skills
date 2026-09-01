import json
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "movie-organizing"
AUDIT_SCRIPT = SKILL_DIR / "scripts" / "movie_organizing_audit.py"
PREPROCESSOR_SCRIPT = SKILL_DIR / "scripts" / "movie_organizing_preprocessor.py"

_AUDIT_SPEC = importlib.util.spec_from_file_location("movie_organizing_audit_module", AUDIT_SCRIPT)
if _AUDIT_SPEC is None or _AUDIT_SPEC.loader is None:
    raise RuntimeError("movie_organizing_audit.py not found")
AUDIT_MODULE = importlib.util.module_from_spec(_AUDIT_SPEC)
_AUDIT_SPEC.loader.exec_module(AUDIT_MODULE)


class MovieOrganizingAuditTest(unittest.TestCase):
    def _make(self, root: Path, relative: str, content: bytes = b"x") -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _audit(self, root: Path):
        process = subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT), "audit", "--task-root", str(root)],
            capture_output=True,
            text=True,
        )
        try:
            report = json.loads(process.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - useful RED output
            self.fail(f"audit did not emit JSON (rc={process.returncode}): {process.stderr}: {exc}")
        return process, report

    def _add_standard_movie(
        self,
        root: Path,
        director: str,
        folder: str,
        video: str,
    ) -> Path:
        movie_dir = root / director / folder
        self._make(movie_dir, video)
        return movie_dir

    def _add_verified_nfo(self, root: Path, movie_dir: Path, tmdb_id: int) -> None:
        """Seed formal NFO identity evidence for gates that reach dedupe/cleanup."""

        videos = [item for item in movie_dir.iterdir() if item.is_file() and item.suffix.casefold() == ".mkv"]
        self.assertEqual(1, len(videos), movie_dir)
        video = videos[0]
        year_match = re.search(r"(?<!\d)(19\d{2}|20\d{2})(?=\.|$)", video.stem)
        self.assertIsNotNone(year_match, video)
        year = year_match.group(1)
        original_title = video.stem[: year_match.start()].rstrip(".")
        nfo = video.with_suffix(".nfo")
        nfo.write_text(
            f'<movie><title>{movie_dir.name.split(".", 1)[0]}</title>'
            f"<originaltitle>{original_title}</originaltitle><year>{year}</year>"
            f'<uniqueid type="tmdb">{tmdb_id}</uniqueid></movie>',
            encoding="utf-8",
        )
        video_stat = video.stat()
        lock = {
            "schema": "movie-organizing-nfo/identity-lock/v1",
            "version": "1.3.6",
            "task_root": str(root.resolve()),
            "plan_hash": f"fixture-{tmdb_id}",
            "verified_at": "fixture",
            "locks": [
                {
                    "video_path": str(video.resolve()),
                    "nfo_path": str(nfo.resolve()),
                    "video_fingerprint": {
                        "path": str(video.resolve()),
                        "exists": True,
                        "size": video_stat.st_size,
                        "mtime_ns": video_stat.st_mtime_ns,
                    },
                    "nfo_sha256": hashlib.sha256(nfo.read_bytes()).hexdigest(),
                    "tmdb_id": tmdb_id,
                }
            ],
        }
        recovery = root / "_work-record_" / "recovery"
        recovery.mkdir(parents=True, exist_ok=True)
        (recovery / f"nfo-identity-lock-fixture-{tmdb_id}.json").write_text(
            json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def test_active_exception_blocks_core_and_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make(
                root / "导演 Director",
                "NoChineseTitle.2020.1080p.WEB-DL.x264-RLS.mkv",
            )

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", report["core_gate"]["status"])
            self.assertGreaterEqual(report["core_gate"]["counts"]["active_exception_units"], 1)
            self.assertEqual("NOT_RUN", report["dedupe_gate"]["status"])
            self.assertEqual("BLOCKED", report["completion_status"])
            self.assertEqual("未完成：仍有核心问题或重复候选", report["allowed_completion_message"])

    def test_cross_directory_same_cn_year_different_english_is_unresolved_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_folder = "费拉特吸血鬼.Upir z Feratu.1982.DVD"
            first_video = "Upir z Feratu.1982.DVD.mkv"
            second_folder = "费拉特吸血鬼.ferat vampire.1982.1080p.BluRay.x264-RLS"
            second_video = "ferat vampire.1982.1080p.BluRay.x264-RLS.mkv"
            first = self._add_standard_movie(root, "捷克导演 Czech Director", first_folder, first_video)
            second = self._add_standard_movie(root, "捷克导演 Czech Director", second_folder, second_video)
            self._add_verified_nfo(root, first, 1001)
            self._add_verified_nfo(root, second, 1002)

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("PASS", report["core_gate"]["status"])
            self.assertEqual("FAIL", report["dedupe_gate"]["status"])
            self.assertEqual(1, report["dedupe_gate"]["counts"]["unresolved_duplicate_groups_in_active_tree"])
            groups = report["dedupe_gate"]["candidate_groups"]
            self.assertEqual(1, len(groups))
            self.assertEqual(
                {str(first.resolve()), str(second.resolve())},
                set(groups[0]["members"]),
            )
            self.assertEqual("BLOCKED", report["completion_status"])
            self.assertEqual("未完成：仍有核心问题或重复候选", report["allowed_completion_message"])

    def test_duplicate_group_zeroes_after_one_member_moves_to_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self._add_standard_movie(
                root,
                "捷克导演 Czech Director",
                "费拉特吸血鬼.Upir z Feratu.1982.DVD",
                "Upir z Feratu.1982.DVD.mkv",
            )
            second = self._add_standard_movie(
                root,
                "捷克导演 Czech Director",
                "费拉特吸血鬼.ferat vampire.1982.1080p.BluRay.x264-RLS",
                "ferat vampire.1982.1080p.BluRay.x264-RLS.mkv",
            )
            self._add_verified_nfo(root, first, 1001)
            pending_parent = root / "_待确认_" / "捷克导演"
            pending_parent.mkdir(parents=True)
            shutil.move(str(second), str(pending_parent / second.name))

            process, report = self._audit(root)

            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", report["core_gate"]["status"])
            self.assertEqual("PASS", report["dedupe_gate"]["status"])
            self.assertEqual(0, report["dedupe_gate"]["counts"]["unresolved_duplicate_groups_in_active_tree"])
            self.assertEqual(1, report["pending_count"])
            self.assertEqual("CORE_COMPLETE_PENDING", report["completion_status"])
            self.assertEqual(
                "主目录五项核心整理已完成，待确认 1项",
                report["allowed_completion_message"],
            )
            self.assertTrue((root / "捷克导演 Czech Director" / first.name).is_dir())

    def test_completion_has_three_states_and_verify_pass_is_naming_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = self._add_standard_movie(
                root,
                "导演 Director",
                "标准片.Standard Movie.2020.1080p.BluRay.x264-RLS",
                "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv",
            )
            self._add_verified_nfo(root, movie, 1001)
            process, report = self._audit(root)
            self.assertEqual(0, process.returncode)
            self.assertEqual("COMPLETE", report["completion_status"])
            self.assertEqual(
                "全部整理完成（待确认=0且终扫PASS）",
                report["allowed_completion_message"],
            )

            plan_process = subprocess.run(
                [sys.executable, str(PREPROCESSOR_SCRIPT), "plan", "--task-root", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            plan_path = json.loads(plan_process.stdout)["plan_path"]
            dry_run_process = subprocess.run(
                [
                    sys.executable,
                    str(PREPROCESSOR_SCRIPT),
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
            self.assertEqual("PASS", json.loads(dry_run_process.stdout)["status"])
            apply_process = subprocess.run(
                [
                    sys.executable,
                    str(PREPROCESSOR_SCRIPT),
                    "apply",
                    "--task-root",
                    str(root),
                    "--plan",
                    plan_path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual("PASS", json.loads(apply_process.stdout)["status"])
            verify_process = subprocess.run(
                [
                    sys.executable,
                    str(PREPROCESSOR_SCRIPT),
                    "verify",
                    "--task-root",
                    str(root),
                    "--plan",
                    plan_path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            verify_report = json.loads(verify_process.stdout)
            self.assertTrue(verify_report["naming_plan_only"])
            self.assertNotIn("allowed_completion_message", verify_report)

    def test_missing_task_root_is_blocked_without_creating_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "does-not-exist"

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertFalse(root.exists())
            self.assertEqual("FAIL", report["status"])
            self.assertEqual("BLOCKED", report["completion_status"])
            self.assertEqual("NOT_RUN", report["dedupe_gate"]["status"])
            self.assertEqual("未完成：仍有核心问题或重复候选", report["allowed_completion_message"])

    def test_report_write_failure_forces_blocked_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._add_standard_movie(
                root,
                "导演 Director",
                "标准片.Standard Movie.2020.1080p.BluRay.x264-RLS",
                "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv",
            )

            with mock.patch.object(AUDIT_MODULE, "_write_report", side_effect=OSError("disk full")):
                report, exit_code = AUDIT_MODULE.audit_task_root(root)

            self.assertNotEqual(0, exit_code)
            self.assertEqual("FAIL", report["status"])
            self.assertEqual("BLOCKED", report["completion_status"])
            self.assertEqual("未完成：仍有核心问题或重复候选", report["allowed_completion_message"])

    def test_cleanup_gate_blocks_non_whitelist_file_then_completes_after_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = self._add_standard_movie(
                root,
                "导演 Director",
                "标准片.Standard Movie.2020.1080p.BluRay.x264-RLS",
                "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv",
            )
            self._add_verified_nfo(root, movie, 1001)
            poster = self._make(movie, "poster.jpg", b"poster")

            blocked_process, blocked_report = self._audit(root)

            self.assertNotEqual(0, blocked_process.returncode)
            self.assertEqual("PASS", blocked_report["core_gate"]["status"])
            self.assertEqual("PASS", blocked_report["dedupe_gate"]["status"])
            self.assertEqual("FAIL", blocked_report["cleanup_gate"]["status"])
            self.assertEqual("BLOCKED", blocked_report["completion_status"])

            poster.unlink()
            complete_process, complete_report = self._audit(root)

            self.assertEqual(0, complete_process.returncode)
            self.assertEqual("PASS", complete_report["cleanup_gate"]["status"])
            self.assertEqual("COMPLETE", complete_report["completion_status"])
            self.assertEqual("全部整理完成（待确认=0且终扫PASS）", complete_report["allowed_completion_message"])

    def test_nonconforming_director_folder_blocks_core_before_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._add_standard_movie(
                root,
                "捷克导演.Czech Director",
                "标准片.Standard Movie.2020.1080p.BluRay.x264-RLS",
                "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv",
            )

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", report["core_gate"]["status"])
            self.assertEqual(1, report["core_gate"]["counts"]["active_nonconforming_director_dirs"])
            self.assertEqual("NOT_RUN", report["dedupe_gate"]["status"])
            self.assertEqual("NOT_RUN", report["cleanup_gate"]["status"])
            self.assertEqual("BLOCKED", report["completion_status"])

    def test_skill_command_chain_includes_dry_run_before_apply(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        # Assert the documented phase order without coupling the contract to a
        # placeholder glob.  The CLI emits a concrete recovery plan path and
        # the task entrypoint is the authoritative workflow gate.
        patterns = [
            r'python3 "\$SCRIPT" plan --task-root "\$TASK_ROOT"',
            r'python3 "\$SCRIPT" apply --task-root "\$TASK_ROOT" --dry-run --plan [^\n]+',
            r'python3 "\$SCRIPT" apply --task-root "\$TASK_ROOT" --plan [^\n]+',
            r'python3 "\$SCRIPT" verify --task-root "\$TASK_ROOT" --plan [^\n]+',
            r'python3 "\$SKILL_DIR/scripts/movie_organizing_audit\.py" audit --task-root "\$TASK_ROOT"',
        ]
        import re

        positions = []
        for pattern in patterns:
            match = re.search(pattern, skill_text)
            self.assertIsNotNone(match, pattern)
            positions.append(match.start())
        self.assertNotIn("plan-*", skill_text)
        self.assertEqual(sorted(positions), positions)

    def test_cleanup_gate_scans_root_and_director_shallow_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = self._add_standard_movie(
                root,
                "导演 Director",
                "标准片.Standard Movie.2020.1080p.BluRay.x264-RLS",
                "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv",
            )
            self._add_verified_nfo(root, movie, 1001)
            root_junk = self._make(root, "root-junk.txt", b"junk")
            director_junk = self._make(root / "导演 Director", "director-junk.txt", b"junk")

            blocked_process, blocked_report = self._audit(root)

            self.assertNotEqual(0, blocked_process.returncode)
            self.assertEqual("PASS", blocked_report["core_gate"]["status"])
            self.assertEqual("PASS", blocked_report["dedupe_gate"]["status"])
            self.assertEqual("FAIL", blocked_report["cleanup_gate"]["status"])
            self.assertGreaterEqual(
                blocked_report["cleanup_gate"]["counts"]["active_non_whitelist_items"],
                2,
            )
            self.assertEqual("BLOCKED", blocked_report["completion_status"])

            root_junk.unlink()
            director_junk.unlink()
            complete_process, complete_report = self._audit(root)

            self.assertEqual(0, complete_process.returncode)
            self.assertEqual("PASS", complete_report["cleanup_gate"]["status"])
            self.assertEqual("COMPLETE", complete_report["completion_status"])

    def test_empty_root_nonvideo_and_unknown_active_directory_block_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root_junk = self._make(root, "root-junk.txt", b"junk")

            blocked_process, blocked_report = self._audit(root)

            self.assertNotEqual(0, blocked_process.returncode)
            self.assertEqual("FAIL", blocked_report["core_gate"]["status"])
            self.assertEqual("NOT_RUN", blocked_report["dedupe_gate"]["status"])
            self.assertEqual("NOT_RUN", blocked_report["cleanup_gate"]["status"])
            self.assertEqual("BLOCKED", blocked_report["completion_status"])

            root_junk.unlink()
            unknown = root / "未知空目录"
            unknown.mkdir()
            blocked_process, blocked_report = self._audit(root)

            self.assertNotEqual(0, blocked_process.returncode)
            self.assertEqual("FAIL", blocked_report["core_gate"]["status"])
            self.assertEqual("NOT_RUN", blocked_report["cleanup_gate"]["status"])
            self.assertEqual("BLOCKED", blocked_report["completion_status"])

            unknown.rmdir()
            complete_process, complete_report = self._audit(root)

            self.assertNotEqual(0, complete_process.returncode)
            self.assertEqual("FAIL", complete_report["core_gate"]["status"])
            self.assertEqual("BLOCKED", complete_report["completion_status"])

    def test_recovery_report_contains_its_own_report_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = self._add_standard_movie(
                root,
                "导演 Director",
                "标准片.Standard Movie.2020.1080p.BluRay.x264-RLS",
                "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv",
            )
            self._add_verified_nfo(root, movie, 1001)

            process, report = self._audit(root)

            self.assertEqual(0, process.returncode)
            report_path = Path(report["report_path"])
            self.assertTrue(report_path.is_file())
            persisted = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(str(report_path), persisted["report_path"])

    def test_pending_symlink_outside_root_blocks_without_following(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external_tmp:
            root = Path(tmp)
            external = Path(external_tmp)
            self._add_standard_movie(
                root,
                "导演 Director",
                "标准片.Standard Movie.2020.1080p.BluRay.x264-RLS",
                "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv",
            )
            self._make(external, "outside.mkv", b"outside")
            os.symlink(str(external), str(root / "_待确认_"), target_is_directory=True)

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", report["status"])
            self.assertEqual("BLOCKED", report["completion_status"])
            self.assertNotEqual("CORE_COMPLETE_PENDING", report["completion_status"])
            self.assertIn("audit_error", report)

    def test_cleanup_gate_detects_expected_video_removed_between_plan_and_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = self._add_standard_movie(
                root,
                "导演 Director",
                "标准片.Standard Movie.2020.1080p.BluRay.x264-RLS",
                "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv",
            )
            self._add_verified_nfo(root, movie, 1001)
            expected_video = movie / "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv"

            def remove_expected_video(_root, _plan):
                expected_video.unlink()
                return []

            with mock.patch.object(AUDIT_MODULE, "_candidate_groups", side_effect=remove_expected_video):
                report, exit_code = AUDIT_MODULE.audit_task_root(root)

            self.assertNotEqual(0, exit_code)
            self.assertEqual("FAIL", report["cleanup_gate"]["status"])
            self.assertGreaterEqual(
                report["cleanup_gate"]["counts"]["active_non_whitelist_items"],
                1,
            )
            self.assertEqual("BLOCKED", report["completion_status"])

    def test_nonempty_pending_without_video_prevents_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending = root / "_待确认_"
            self._make(pending, "note.txt", b"needs review")

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertGreaterEqual(report["pending_count"], 1)
            self.assertGreaterEqual(report.get("pending_nonvideo_or_empty_units", 0), 1)
            self.assertEqual("BLOCKED", report["completion_status"])
            self.assertEqual("FAIL", report["core_gate"]["status"])
            self.assertNotEqual("COMPLETE", report["completion_status"])

    def test_empty_active_root_blocks_core_and_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", report["status"])
            self.assertEqual("FAIL", report["core_gate"]["status"])
            self.assertEqual(0, report["core_gate"]["counts"]["active_video_units"])
            self.assertIn("active video", report["core_gate"].get("reason", "").lower())
            self.assertEqual("NOT_RUN", report["dedupe_gate"]["status"])
            self.assertEqual("NOT_RUN", report["cleanup_gate"]["status"])
            self.assertEqual("BLOCKED", report["completion_status"])

    def test_nested_control_directories_are_active_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = self._add_standard_movie(
                root,
                "导演 Director",
                "标准片.Standard Movie.2020.1080p.BluRay.x264-RLS",
                "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv",
            )
            self._add_verified_nfo(root, movie, 1001)
            self._make(root / "导演 Director" / "_待确认_", "hidden.mkv")
            self._make(root / "导演 Director" / "_trash_nested", "hidden.mkv")
            self._make(movie / "_work-record_", "hidden.mkv")

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", report["cleanup_gate"]["status"])
            self.assertGreaterEqual(report["cleanup_gate"]["counts"]["active_non_whitelist_items"], 3)
            self.assertEqual("BLOCKED", report["completion_status"])

    def test_work_record_video_is_a_control_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make(root / "_work-record_", "hidden.mkv")

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", report["status"])
            self.assertGreaterEqual(report["control_violation_count"], 1)
            self.assertTrue(any("video" in item["reason"].lower() for item in report["control_violations"]))
            self.assertEqual("BLOCKED", report["completion_status"])

    def test_root_trash_video_is_excluded_from_active_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make(root / "_trash_20260828", "old.mkv")

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("BLOCKED", report["completion_status"])
            self.assertEqual("FAIL", report["core_gate"]["status"])
            self.assertEqual(0, report["pending_count"])
            self.assertEqual(0, report["core_gate"]["counts"]["active_video_units"])

    def test_pending_video_counts_as_pending_not_active_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make(root / "_待确认_", "review.mkv")

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual(1, report["pending_count"])
            self.assertEqual(1, report["pending_video_count"])
            self.assertEqual("BLOCKED", report["completion_status"])
            self.assertEqual("FAIL", report["core_gate"]["status"])
            self.assertEqual("NOT_RUN", report["cleanup_gate"]["status"])
            self.assertEqual(0, report["core_gate"]["counts"]["active_video_units"])

    def test_dirty_whole_pending_remains_blocked_with_real_video_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending_unit = root / "_待确认_" / "脏容器"
            self._make(pending_unit, "Dirty.Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            self._make(pending_unit, "notes.txt", b"keep for review")

            process, report = self._audit(root)

            self.assertNotEqual(0, process.returncode)
            self.assertEqual("BLOCKED", report["completion_status"])
            self.assertEqual("FAIL", report["core_gate"]["status"])
            self.assertEqual(1, report["pending_video_count"])

    def test_v134_audit_requires_middle_dot_for_foreign_chinese_director_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._add_standard_movie(
                root,
                "爱德嘉 莱兹 Edgar Reitz",
                "影.Original Movie.1949.1080p.BluRay.x264-RLS",
                "Original Movie.1949.1080p.BluRay.x264-RLS.mkv",
            )
            process, report = self._audit(root)
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", report["core_gate"]["status"])
            self.assertGreaterEqual(report["core_gate"]["counts"]["active_nonconforming_director_dirs"], 1)
            self.assertEqual("BLOCKED", report["completion_status"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = self._add_standard_movie(
                root,
                "爱德嘉·莱兹 Edgar Reitz",
                "影.Original Movie.1949.1080p.BluRay.x264-RLS",
                "Original Movie.1949.1080p.BluRay.x264-RLS.mkv",
            )
            self._add_verified_nfo(root, movie, 1001)
            process, report = self._audit(root)
            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", report["core_gate"]["status"])
            self.assertEqual("COMPLETE", report["completion_status"])

    def test_v134_audit_requires_exactly_one_ascii_space_at_director_boundary(self):
        invalid_names = (
            "爱德嘉·莱兹  Edgar Reitz",
            "爱德嘉·莱兹\tEdgar Reitz",
            "爱德嘉·莱兹Edgar Reitz",
        )
        for director in invalid_names:
            with self.subTest(director=director), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._add_standard_movie(
                    root,
                    director,
                    "影.Original Movie.1949.1080p.BluRay.x264-RLS",
                    "Original Movie.1949.1080p.BluRay.x264-RLS.mkv",
                )
                process, report = self._audit(root)
                self.assertNotEqual(0, process.returncode)
                self.assertEqual("FAIL", report["core_gate"]["status"])
                self.assertGreaterEqual(report["core_gate"]["counts"]["active_nonconforming_director_dirs"], 1)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = self._add_standard_movie(
                root,
                "爱德嘉·莱兹 Edgar Reitz",
                "影.Original Movie.1949.1080p.BluRay.x264-RLS",
                "Original Movie.1949.1080p.BluRay.x264-RLS.mkv",
            )
            self._add_verified_nfo(root, movie, 1001)
            process, report = self._audit(root)
            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", report["core_gate"]["status"])

    def test_v134_wrapper_residue_after_flatten_blocks_cleanup_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = self._add_standard_movie(
                root,
                "导演 Director",
                "outer1/outer2/标准片.Standard Movie.2020.1080p.BluRay.x264-RLS",
                "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv",
            )
            # This models wrappers left after a nested movie has been moved to
            # the director root; cleanup must not silently treat them as done.
            flattened = root / "导演 Director" / "标准片.Standard Movie.2020.1080p.BluRay.x264-RLS"
            movie.rename(flattened)
            self._add_verified_nfo(root, flattened, 1001)

            process, report = self._audit(root)
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("PASS", report["core_gate"]["status"])
            self.assertEqual("PASS", report["dedupe_gate"]["status"])
            self.assertEqual("FAIL", report["cleanup_gate"]["status"])
            self.assertGreaterEqual(report["cleanup_gate"]["counts"]["active_non_whitelist_items"], 1)
            self.assertEqual("BLOCKED", report["completion_status"])

    def test_install_verifier_rejects_truncated_or_tampered_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied_skill = Path(tmp) / "movie-organizing"
            shutil.copytree(SKILL_DIR, copied_skill)
            target = copied_skill / "scripts" / "movie_organizing_preprocessor.py"
            with target.open("ab") as stream:
                stream.write(b"\n[OUTPUT TRUNCATED ...]\n")

            process = subprocess.run(
                [
                    sys.executable,
                    str(AUDIT_SCRIPT),
                    "verify-install",
                    "--skill-dir",
                    str(copied_skill),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, process.returncode)
            report = json.loads(process.stdout)
            self.assertEqual("FAIL", report["status"])
            self.assertTrue(
                any("truncat" in failure.lower() or "hash" in failure.lower() for failure in report["failures"])
            )

    def test_install_verifier_rejects_manifest_missing_required_script_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied_skill = Path(tmp) / "movie-organizing"
            shutil.copytree(SKILL_DIR, copied_skill)
            manifest_path = copied_skill / "integrity-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest["files"]:
                target = copied_skill / entry["path"]
                data = target.read_bytes()
                entry["size"] = len(data)
                entry["sha256"] = hashlib.sha256(data).hexdigest()
            manifest["files"] = [
                entry
                for entry in manifest["files"]
                if entry.get("path") != "scripts/movie_organizing_audit.py"
            ]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            process = subprocess.run(
                [
                    sys.executable,
                    str(AUDIT_SCRIPT),
                    "verify-install",
                    "--skill-dir",
                    str(copied_skill),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, process.returncode)
            report = json.loads(process.stdout)
            self.assertEqual("FAIL", report["status"])
            self.assertTrue(any("required" in failure.lower() for failure in report["failures"]))

    def test_install_verifier_rejects_missing_required_script_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied_skill = Path(tmp) / "movie-organizing"
            shutil.copytree(SKILL_DIR, copied_skill)
            manifest_path = copied_skill / "integrity-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest["files"]:
                target = copied_skill / entry["path"]
                data = target.read_bytes()
                entry["size"] = len(data)
                entry["sha256"] = hashlib.sha256(data).hexdigest()
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            (copied_skill / "scripts" / "movie_organizing_audit.py").unlink()

            process = subprocess.run(
                [
                    sys.executable,
                    str(AUDIT_SCRIPT),
                    "verify-install",
                    "--skill-dir",
                    str(copied_skill),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, process.returncode)
            report = json.loads(process.stdout)
            self.assertEqual("FAIL", report["status"])
            self.assertTrue(any("missing file" in failure.lower() for failure in report["failures"]))


if __name__ == "__main__":
    unittest.main()
