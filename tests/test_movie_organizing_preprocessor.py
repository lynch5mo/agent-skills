import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from importlib.machinery import SourceFileLoader


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "movie-organizing"
    / "scripts"
    / "movie_organizing_preprocessor.py"
)

if not SCRIPT_PATH.exists():
    raise RuntimeError("movie_organizing_preprocessor.py not found")

preprocessor = SourceFileLoader("movie_organizing_preprocessor", str(SCRIPT_PATH)).load_module()


class MovieOrganizingPreprocessorTest(unittest.TestCase):
    def _make(self, root: Path, relative: str, content: bytes = b"x"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _plan(self, root: Path):
        return preprocessor.make_plan(root)

    def _apply(self, plan, root: Path, dry_run: bool = False):
        return preprocessor.apply_plan(plan, root=root, dry_run=dry_run)

    def _verify(self, plan, root: Path):
        return preprocessor.verify_plan(plan, root=root)

    def _find_bundle(self, plan, video_stem: str):
        for item in plan["bundles"]:
            if item.get("expected_video_source", "").endswith(video_stem + ".mkv"):
                return item
            for action in item["actions"]:
                source = action.get("source", "")
                if source.endswith(video_stem + ".mkv"):
                    return item
        raise AssertionError(f"bundle for {video_stem} not found")

    def _run_cli(self, mode: str, root: Path, plan_path: str, *, dry_run: bool = False):
        command = [sys.executable, str(SCRIPT_PATH), mode, "--task-root", str(root), "--plan", plan_path]
        if dry_run:
            command.append("--dry-run")
        return subprocess.run(command, check=True, capture_output=True, text=True)

    def _make_nested_standard(self, root: Path, director: str = "导演 Director"):
        movie_name = "标准片.Standard Movie.2020.1080p.BluRay.x264-RLS"
        video_name = "Standard Movie.2020.1080p.BluRay.x264-RLS.mkv"
        movie_dir = root / director / "outer1" / "outer2" / movie_name
        video = self._make(movie_dir, video_name)
        subtitle = self._make(movie_dir, video_name.removesuffix(".mkv") + ".chs.srt")
        return movie_dir, video, subtitle, movie_name, video_name

    def test_v134_normalizes_foreign_director_and_flattens_then_audits_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_director = root / "爱德嘉 莱兹 Edgar Reitz"
            movie_dir = old_director / "旧外壳" / "影.Original Movie.1949.1080p.BluRay.x264-RLS"
            video = self._make(movie_dir, "Original Movie.1949.1080p.BluRay.x264-RLS.mkv")

            plan = self._plan(root)
            self.assertEqual("1.3.6", plan["version"])
            self.assertEqual(1, len(plan.get("director_actions", [])))
            director_action = plan["director_actions"][0]
            self.assertEqual(str(old_director.resolve()), director_action["source"])
            self.assertEqual(str((root / "爱德嘉·莱兹 Edgar Reitz").resolve()), director_action["target"])
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("dispersed", bundle["source_shape"])
            self.assertEqual(
                str((root / "爱德嘉·莱兹 Edgar Reitz" / bundle["expected_movie_dir"]).resolve()),
                bundle["expected_movie_dir_path"],
            )

            plan_path = plan["plan_path"]
            dry_run = self._run_cli("apply", root, plan_path, dry_run=True)
            self.assertEqual("PASS", json.loads(dry_run.stdout)["status"])
            applied = self._run_cli("apply", root, plan_path)
            self.assertEqual("PASS", json.loads(applied.stdout)["status"])
            verified = self._run_cli("verify", root, plan_path)
            self.assertEqual("PASS", json.loads(verified.stdout)["status"])

            final_director = root / "爱德嘉·莱兹 Edgar Reitz"
            final_movie = final_director / bundle["expected_movie_dir"]
            self.assertTrue(final_director.is_dir())
            self.assertTrue((final_movie / video.name).is_file())
            self.assertFalse(old_director.exists())
            self.assertFalse(movie_dir.exists())
            final_video = final_movie / video.name
            final_nfo = final_video.with_suffix(".nfo")
            final_nfo.write_text(
                '<movie><title>影</title><originaltitle>Original Movie</originaltitle>'
                '<year>1949</year><uniqueid type="tmdb">1001</uniqueid></movie>',
                encoding="utf-8",
            )
            video_stat = final_video.stat()
            lock = {
                "schema": "movie-organizing-nfo/identity-lock/v1",
                "version": "1.3.6",
                "task_root": str(root.resolve()),
                "plan_hash": "fixture-1001",
                "verified_at": "fixture",
                "locks": [
                    {
                        "video_path": str(final_video.resolve()),
                        "nfo_path": str(final_nfo.resolve()),
                        "video_fingerprint": {
                            "path": str(final_video.resolve()),
                            "exists": True,
                            "size": video_stat.st_size,
                            "mtime_ns": video_stat.st_mtime_ns,
                        },
                        "nfo_sha256": hashlib.sha256(final_nfo.read_bytes()).hexdigest(),
                        "tmdb_id": 1001,
                    }
                ],
            }
            recovery = root / "_work-record_" / "recovery"
            (recovery / "nfo-identity-lock-fixture.json").write_text(
                json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            audit = subprocess.run(
                [sys.executable, str(SCRIPT_PATH.parent / "movie_organizing_audit.py"), "audit", "--task-root", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(audit.stdout)
            self.assertEqual("COMPLETE", report["completion_status"])

    def test_v134_director_middle_dot_rules_preserve_native_and_multi_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures = {
                "阿布戴·柯西胥 Abdel Kechiche": "Abdel.Movie.2020.1080p.WEB-DL.x264-RLS",
                "刁亦男 Yi'nan Diao": "Diao.Movie.2020.1080p.WEB-DL.x264-RLS",
                "奥利弗·纳卡什、艾力克·托莱达诺 Olivier Nakache、Éric Toledano": "Multi.Movie.2020.1080p.WEB-DL.x264-RLS",
                "张艺谋 Zhang Yimou": "Native.Movie.2020.1080p.WEB-DL.x264-RLS",
            }
            for director, stem in fixtures.items():
                movie = root / director / f"中文片.{stem}"
                self._make(movie, f"{stem}.mkv")

            plan = self._plan(root)
            self.assertEqual([], plan.get("director_actions", []))
            self.assertEqual(
                {director for director in fixtures},
                {Path(item["source_director_dir"]).name for item in plan["bundles"]},
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / "爱德嘉.莱兹 Edgar Reitz"
            stem = "Original.Movie.1949.1080p.BluRay.x264-RLS"
            self._make(bad / f"中文片.{stem}", f"{stem}.mkv")
            plan = self._plan(root)
            self.assertEqual(1, len(plan["director_actions"]))
            self.assertEqual("爱德嘉·莱兹 Edgar Reitz", Path(plan["director_actions"][0]["target"]).name)

    def test_v134_director_migration_rejects_ambiguous_boundary_or_foreign_symbols(self):
        for director in ("爱德嘉 莱兹", "爱德嘉 # 莱兹 Edgar Reitz"):
            with self.subTest(director=director), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                leaf = root / director / "中文片.Movie.2020.1080p.WEB-DL.x264-RLS"
                video = self._make(leaf, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
                plan = self._plan(root)
                bundle = self._find_bundle(plan, video.stem)
                self.assertEqual("EXCEPTION", bundle["status"])
                self.assertFalse(bundle["actions"])
                self.assertEqual([], plan["director_actions"])
                self.assertTrue(video.exists())

    def test_v134_nested_standard_movie_is_rehomed_to_director_root_with_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_movie, video, subtitle, movie_name, video_name = self._make_nested_standard(root)
            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("dispersed", bundle["source_shape"])
            self.assertEqual(str((root / "导演 Director" / movie_name).resolve()), bundle["expected_movie_dir_path"])
            self.assertEqual("ACTION_REQUIRED", bundle["status"])
            result = self._apply(plan, root)
            self.assertEqual("PASS", result["status"])
            final_movie = root / "导演 Director" / movie_name
            self.assertTrue((final_movie / video_name).is_file())
            self.assertTrue((final_movie / (video.stem + ".chs.srt")).is_file())
            self.assertFalse(old_movie.exists())
            self.assertFalse((root / "导演 Director" / "outer1").exists())
            self.assertTrue((root / "_work-record_" / "flattened-empty").is_dir())

    def test_v134_nested_nonstandard_with_filename_prefix_or_nfo_is_rehomed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            director = root / "导演 Director"
            prefix_video = self._make(
                director / "wrapper" / "legacy-prefix",
                "中文前缀.Prefix Movie.2021.1080p.WEB-DL.x264-RLS.mkv",
            )
            nfo_video = self._make(
                director / "wrapper" / "legacy-nfo",
                "Nfo.Movie.2022.1080p.WEB-DL.x264-RLS.mkv",
            )
            self._make(
                nfo_video.parent,
                nfo_video.stem + ".nfo",
                "<movie><title>NFO 中文片</title></movie>".encode(),
            )
            plan = self._plan(root)
            prefix_bundle = self._find_bundle(plan, prefix_video.stem)
            nfo_bundle = self._find_bundle(plan, nfo_video.stem)
            self.assertEqual("dispersed", prefix_bundle["source_shape"])
            self.assertEqual("dispersed", nfo_bundle["source_shape"])
            self.assertEqual("PASS", self._apply(plan, root)["status"])
            self.assertTrue((director / prefix_bundle["expected_movie_dir"] / "Prefix Movie.2021.1080p.WEB-DL.x264-RLS.mkv").is_file())
            self.assertTrue((director / nfo_bundle["expected_movie_dir"] / "Nfo Movie.2022.1080p.WEB-DL.x264-RLS.nfo").is_file())
            self.assertFalse(prefix_video.exists())
            self.assertFalse(nfo_video.exists())

    def test_v134_nested_ambiguous_units_remain_exception_without_mutation(self):
        scenarios = ("collision", "multi", "no-chinese")
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                director = root / "导演 Director"
                if scenario == "collision":
                    stem = "Collision.Movie.2020.1080p.WEB-DL.x264-RLS"
                    source = self._make(director / "wrapper" / "legacy", stem + ".mkv")
                    (director / ("中文片." + stem)).mkdir(parents=True)
                elif scenario == "multi":
                    source = self._make(director / "wrapper" / "legacy", "中文片.Movie.2020.1080p.WEB-DL.x264-A.mkv")
                    self._make(source.parent, "中文片.Movie.2020.1080p.WEB-DL.x264-B.mkv")
                else:
                    source = self._make(director / "wrapper" / "legacy", "NoChinese.Movie.2020.1080p.WEB-DL.x264-RLS.mkv")

                plan = self._plan(root)
                bundle = self._find_bundle(plan, source.stem)
                self.assertEqual("EXCEPTION", bundle["status"])
                self.assertFalse(bundle["actions"])
                self.assertTrue(source.exists())
                self.assertEqual([], plan.get("director_actions", []))

    def test_v134_shared_wrapper_is_archived_once_after_all_leaf_rehomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            director = root / "导演 Director"
            leaves = []
            for index in (1, 2):
                movie_name = f"片{index}.Movie {index}.2020.1080p.BluRay.x264-RLS"
                video_name = f"Movie {index}.2020.1080p.BluRay.x264-RLS.mkv"
                leaf = director / "shared-wrapper" / f"legacy-{index}" / movie_name
                leaves.append((leaf, movie_name, video_name))
                self._make(leaf, video_name)

            plan = self._plan(root)
            self.assertEqual(1, sum(action.get("action") == "rename_dir" for action in plan["wrapper_actions"]))
            self.assertEqual(2, len([item for item in plan["bundles"] if item["status"] == "ACTION_REQUIRED"]))
            self.assertEqual("PASS", self._apply(plan, root)["status"])
            self.assertFalse((director / "shared-wrapper").exists())
            archives = list((root / "_work-record_" / "flattened-empty").iterdir())
            self.assertEqual(1, len(archives))
            self.assertTrue((archives[0] / "legacy-1").is_dir())
            self.assertTrue((archives[0] / "legacy-2").is_dir())
            for _leaf, movie_name, video_name in leaves:
                self.assertTrue((director / movie_name / video_name).is_file())

    def test_v134_unknown_wrapper_file_blocks_related_flatten_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            director = root / "导演 Director"
            leaf = director / "wrapper" / "legacy" / "片.Movie.2020.1080p.BluRay.x264-RLS"
            video = self._make(leaf, "Movie.2020.1080p.BluRay.x264-RLS.mkv")
            junk = self._make(director / "wrapper", "unknown.txt", b"do not hide")

            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("EXCEPTION", bundle["status"])
            self.assertIn("unaccounted", bundle["exception"])
            self.assertFalse(bundle["actions"])
            self.assertEqual([], plan["wrapper_actions"])
            self.assertEqual("PASS", self._apply(plan, root)["status"])
            self.assertTrue(video.exists())
            self.assertTrue(junk.exists())

    def _apply_with_wrapper_injection(self, root: Path, movie_dir: Path, kind: str):
        """Inject an entry immediately after the child movie rename."""

        plan = self._plan(root)
        wrapper = movie_dir.parents[1]
        injected = wrapper / ("injected-unknown.txt" if kind == "file" else "injected-link")
        original_rename = Path.rename

        def rename_with_injection(source, target):
            result = original_rename(source, target)
            if Path(source).resolve() == movie_dir.resolve():
                if kind == "file":
                    injected.write_bytes(b"arrived after the scan")
                else:
                    os.symlink("/outside/task-root", str(injected))
            return result

        with mock.patch.object(Path, "rename", new=rename_with_injection):
            result = self._apply(plan, root)
        return result, plan, wrapper, injected

    def test_v134_wrapper_recheck_rejects_unknown_file_arriving_after_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_director = "爱德嘉 莱兹 Edgar Reitz"
            movie_dir, _video, _subtitle, _movie_name, _video_name = self._make_nested_standard(root, old_director)
            result, plan, wrapper, injected = self._apply_with_wrapper_injection(root, movie_dir, "file")

            self.assertEqual("FAIL", result["status"])
            self.assertIn("wrapper", result["error_summary"].lower())
            self.assertTrue(wrapper.is_dir())
            self.assertTrue(injected.is_file())
            archive_target = next(
                action["target"] for action in plan["wrapper_actions"] if action["action"] == "rename_dir"
            )
            self.assertFalse(Path(archive_target).exists())
            self.assertTrue((root / old_director).is_dir())
            self.assertFalse((root / "爱德嘉·莱兹 Edgar Reitz").exists())
            self.assertTrue(plan["director_actions"])

    def test_v134_wrapper_recheck_rejects_symlink_arriving_after_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_director = "爱德嘉 莱兹 Edgar Reitz"
            movie_dir, _video, _subtitle, _movie_name, _video_name = self._make_nested_standard(root, old_director)
            result, plan, wrapper, injected = self._apply_with_wrapper_injection(root, movie_dir, "symlink")

            self.assertEqual("FAIL", result["status"])
            self.assertIn("wrapper", result["error_summary"].lower())
            self.assertTrue(wrapper.is_dir())
            self.assertTrue(os.path.lexists(injected))
            self.assertTrue(injected.is_symlink())
            self.assertTrue((root / old_director).is_dir())
            self.assertFalse((root / "爱德嘉·莱兹 Edgar Reitz").exists())
            self.assertTrue(plan["director_actions"])

    def test_v134_apply_rejects_symlink_source_or_target_before_mutation(self):
        for kind in ("source", "target"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
                root = Path(tmp)
                movie_dir = root / "导演 Director" / "标准片.Standard Movie.2020"
                video = self._make(movie_dir, "Standard.Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
                plan = self._plan(root)
                bundle = self._find_bundle(plan, video.stem)
                action = next(item for item in bundle["actions"] if item["action"] == "move_file")
                external = Path(outside_tmp) / f"movie-organizing-{kind}-outside"
                external.write_bytes(b"outside")
                link = Path(action["source"] if kind == "source" else action["target"])
                link.unlink(missing_ok=True)
                os.symlink(str(external), str(link))

                result = self._apply(plan, root)

                self.assertEqual("FAIL", result["status"])
                self.assertEqual(0, result["executed_actions"])
                self.assertIn("symlink", result["error_summary"].lower())
                self.assertTrue(link.is_symlink())
                external.unlink()

    def test_v134_direct_orphan_wrapper_is_archived_but_standard_movie_dir_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            director = root / "导演 Director"
            orphan_wrapper = director / "orphan-wrapper"
            orphan_video = self._make(orphan_wrapper, "孤儿片.Orphan Movie.2021.1080p.WEB-DL.x264-RLS.mkv")
            plan = self._plan(root)
            orphan_bundle = self._find_bundle(plan, orphan_video.stem)
            self.assertEqual("orphan", orphan_bundle["source_shape"])
            self.assertTrue(any(action["action"] == "rename_dir" for action in plan["wrapper_actions"]))
            self.assertEqual("PASS", self._apply(plan, root)["status"])
            self.assertFalse(orphan_wrapper.exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie_dir = root / "导演 Director" / "标准片.Standard Movie.2020"
            self._make(movie_dir, "Standard Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            plan = self._plan(root)
            self.assertEqual([], plan["wrapper_actions"])
            self.assertEqual("PASS", self._apply(plan, root)["status"])
            self.assertFalse(movie_dir.exists())

    def test_v134_two_nested_leaves_share_one_final_director_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_director = root / "爱德嘉 莱兹 Edgar Reitz"
            leaves = (
                old_director / "outer-a" / "影一.Movie One.1949.1080p.BluRay.x264-RLS",
                old_director / "outer-b" / "影二.Movie Two.1950.1080p.BluRay.x264-RLS",
            )
            for leaf in leaves:
                self._make(leaf, leaf.name.split(".", 1)[1] + ".mkv")
            plan = self._plan(root)

            self.assertEqual(1, len(plan["director_actions"]))
            self.assertEqual(2, sum(action["action"] == "rename_dir" for action in plan["wrapper_actions"]))
            self.assertEqual("PASS", self._apply(plan, root)["status"])
            final_director = root / "爱德嘉·莱兹 Edgar Reitz"
            self.assertTrue(final_director.is_dir())
            self.assertFalse(old_director.exists())
            self.assertEqual(2, len(list(final_director.iterdir())))

    def test_v134_bracket_dir_uses_unicode_latin_boundary_without_contaminating_chinese_title(self):
        for english_title in ("Élan", "Ångström"):
            with self.subTest(english_title=english_title), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                movie_dir = root / f"中文电影 {english_title} (2020)"
                video = self._make(movie_dir, f"{english_title}.2020.1080p.WEB-DL.x264-RLS.mkv")

                plan = self._plan(root)
                bundle = self._find_bundle(plan, video.stem)

                self.assertEqual("ACTION_REQUIRED", bundle["status"])
                self.assertEqual(
                    f"中文电影.{english_title}.2020.1080p.WEB-DL.x264-RLS",
                    bundle["expected_movie_dir"],
                )
                self.assertNotIn("中文电影 É", bundle["expected_movie_dir"])

    def test_v134_bracket_dir_with_cyrillic_title_stays_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie_dir = root / "导演 Director" / "中文电影 Фильм (2020)"
            video = self._make(movie_dir, "Film.2020.1080p.WEB-DL.x264-RLS.mkv")

            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)

            self.assertEqual("EXCEPTION", bundle["status"])
            self.assertFalse(bundle["actions"])
            self.assertTrue(video.exists())

    def test_apply_result_write_failure_is_nonzero_and_preserves_executed_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "影迷.The.Movie.2019"
            video = self._make(src_dir, "The.Movie.2019.1080p.BluRay.x264-GRP.mkv")
            plan = self._plan(root)
            self.assertEqual("ACTION_REQUIRED", self._find_bundle(plan, video.stem)["status"])

            dry_run_output = io.StringIO()
            with contextlib.redirect_stdout(dry_run_output):
                dry_run_exit = preprocessor.main(
                    [
                        "apply",
                        "--task-root",
                        str(root),
                        "--plan",
                        str(plan["plan_path"]),
                        "--dry-run",
                    ]
                )
            self.assertEqual(0, dry_run_exit)

            output = io.StringIO()
            with mock.patch.object(preprocessor, "_write_result", side_effect=OSError("disk full")):
                with contextlib.redirect_stdout(output):
                    exit_code = preprocessor.main(
                        ["apply", "--task-root", str(root), "--plan", str(plan["plan_path"])]
                    )

            result = json.loads(output.getvalue())
            self.assertNotEqual(0, exit_code)
            self.assertEqual("FAIL", result["status"])
            self.assertGreaterEqual(result["executed_actions"], 1)
            self.assertIn("result write failed", result["error_summary"].lower())
            self.assertIn("result_write_error", result)

    def test_verify_result_write_failure_is_nonzero_and_explicitly_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie_dir = root / "导演 Director" / "标准片.Standard Movie.2020.1080p.BluRay.x264-GRP"
            self._make(movie_dir, "Standard Movie.2020.1080p.BluRay.x264-GRP.mkv")
            plan = self._plan(root)
            self.assertEqual("NAMING_PASS", plan["bundles"][0]["status"])

            output = io.StringIO()
            with mock.patch.object(preprocessor, "_write_result", side_effect=OSError("read-only")):
                with contextlib.redirect_stdout(output):
                    exit_code = preprocessor.main(
                        ["verify", "--task-root", str(root), "--plan", str(plan["plan_path"])]
                    )

            result = json.loads(output.getvalue())
            self.assertNotEqual(0, exit_code)
            self.assertEqual("FAIL", result["status"])
            self.assertTrue(result["naming_plan_only"])
            self.assertIn("result write failed", result["error_summary"].lower())
            self.assertIn("result_write_error", result)

    def test_plan_refuses_work_record_or_recovery_symlink_outside_root(self):
        for symlink_target in ("work-record", "recovery"):
            with self.subTest(symlink_target=symlink_target), tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external_tmp:
                root = Path(tmp)
                external = Path(external_tmp)
                movie_dir = root / "导演 Director" / "标准片.Standard Movie.2020.1080p.BluRay.x264-GRP"
                self._make(movie_dir, "Standard Movie.2020.1080p.BluRay.x264-GRP.mkv")
                if symlink_target == "work-record":
                    os.symlink(str(external), str(root / "_work-record_"), target_is_directory=True)
                else:
                    (root / "_work-record_").mkdir()
                    os.symlink(str(external), str(root / "_work-record_" / "recovery"), target_is_directory=True)

                with self.assertRaises(OSError):
                    preprocessor.make_plan(root)

                self.assertEqual([], list(external.iterdir()))

    def test_plan_refuses_contract_hash_drift_before_scan_or_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make(
                root / "中文片.Movie.2020",
                "Movie.2020.1080p.WEB-DL.x264-RLS.mkv",
            )

            with mock.patch.object(preprocessor, "_contract_hash", return_value="tampered"):
                with self.assertRaises(ValueError):
                    preprocessor.make_plan(root)

            self.assertFalse((root / "_work-record_").exists())

    def test_standard_sample_dablova_plan_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "魔鬼的陷阱.Dablova past.1962"
            video = self._make(
                src_dir,
                "Dablova past.1962.720p.HDTV.x264-DON.mkv",
            )

            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("ACTION_REQUIRED", bundle["status"])
            self.assertEqual("standard", bundle["source_shape"])
            self.assertEqual("魔鬼的陷阱.Dablova past.1962.720p.HDTV.x264-DON", bundle["expected_movie_dir"])
            expected_video = src_dir.parent / "魔鬼的陷阱.Dablova past.1962.720p.HDTV.x264-DON" / video.name
            self.assertEqual(expected_video.name, Path(bundle["expected_video_target"]).name)
            self.assertEqual(len(bundle["actions"]), 1)

            result = self._apply(plan, root)
            self.assertEqual("PASS", result["status"])
            self.assertTrue((src_dir.parent / bundle["expected_movie_dir"]).exists())
            self.assertTrue((src_dir.parent / bundle["expected_movie_dir"] / video.name).exists())
            self.assertFalse(src_dir.exists())

            verify = self._verify(plan, root)
            self.assertEqual("PASS", verify["status"])

    def test_video_title_dot_to_space_and_sidecar_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "影迷.The.Dot.Movie.2019"
            video = self._make(src_dir, "The.Dot.Movie.2019.1080p.BluRay.x264-GRP.mkv")
            self._make(src_dir, "The.Dot.Movie.2019.1080p.BluRay.x264-GRP.chs.srt")

            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("ACTION_REQUIRED", bundle["status"])
            self.assertEqual("standard", bundle["source_shape"])
            self.assertEqual(
                "影迷.The Dot Movie.2019.1080p.BluRay.x264-GRP",
                bundle["expected_movie_dir"],
            )
            self.assertEqual(
                "The Dot Movie.2019.1080p.BluRay.x264-GRP.mkv",
                Path(bundle["expected_video_target"]).name,
            )
            self.assertEqual(
                "The Dot Movie.2019.1080p.BluRay.x264-GRP.chs.srt",
                Path(bundle["expected_subtitle_targets"][0]).name,
            )

            result = self._apply(plan, root)
            self.assertEqual("PASS", result["status"])
            expected_dir = Path(root / bundle["expected_movie_dir"])
            self.assertTrue((expected_dir / "The Dot Movie.2019.1080p.BluRay.x264-GRP.mkv").exists())
            self.assertTrue((expected_dir / "The Dot Movie.2019.1080p.BluRay.x264-GRP.chs.srt").exists())

    def test_subtitle_language_alias_is_normalized_without_touching_release_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "影迷.The.Dot.Movie.2019"
            video = self._make(src_dir, "The.Dot.Movie.2019.1080p.BluRay.x264-GRP.mkv")
            self._make(src_dir, video.stem + ".zh.srt")
            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("ACTION_REQUIRED", bundle["status"])
            self.assertEqual(
                "The Dot Movie.2019.1080p.BluRay.x264-GRP.chs.srt",
                Path(bundle["expected_subtitle_targets"][0]).name,
            )
            self.assertEqual("PASS", self._apply(plan, root)["status"])

    def test_subtitle_without_language_marker_is_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "影迷.The.Movie.2019"
            video = self._make(src_dir, "The.Movie.2019.1080p.BluRay.x264-GRP.mkv")
            self._make(src_dir, video.stem + ".srt")
            bundle = self._find_bundle(self._plan(root), video.stem)
            self.assertEqual("EXCEPTION", bundle["status"])
            self.assertIn("language", bundle["exception"].lower())

    def test_bracket_style_dir_is_plan_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文电影 The Movie (2020)"
            video = self._make(src_dir, "The Movie.2020.720p.HDRip.x264-YTS.mkv")

            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("ACTION_REQUIRED", bundle["status"])
            self.assertEqual("standard", bundle["source_shape"])
            self.assertEqual("中文电影.The Movie.2020.720p.HDRip.x264-YTS", bundle["expected_movie_dir"])

    def test_collision_or_year_mismatch_and_multi_video_are_exceptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conflict_dir = root / "中文冲突.Movie.2019"
            conflict_dir.mkdir()
            self._make(conflict_dir, "Movie.2019.720p.BD.x264-RLS.mkv")
            (root / "中文冲突.Movie.2019.720p.BD.x264-RLS").mkdir()
            plan = self._plan(root)
            target = self._find_bundle(plan, "Movie.2019.720p.BD.x264-RLS")
            self.assertEqual("EXCEPTION", target["status"])
            self.assertIn("target exists", target["exception"])

            multi_dir = root / "中文多源.Movie.2021"
            self._make(multi_dir, "Movie.2021.1080p.BluRay.x264-AAA.mkv")
            self._make(multi_dir, "Movie.2021.1080p.WEB-DL.x264-AAA.mkv")
            multi_plan = self._plan(root)
            multi_bundle = next(
                bundle
                for bundle in multi_plan["bundles"]
                if str(Path(bundle["source_movie_dir"])) == str(multi_dir.resolve())
            )
            self.assertEqual("EXCEPTION", multi_bundle["status"])
            self.assertIn("multi-video", multi_bundle["exception"])

    def test_orphan_video_with_chinese_prefix_creates_folder_and_moves_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            director = root / "Christopher Nolan"
            video = self._make(
                director,
                "星际穿越.Interstellar.2014.1080p.BluRay.x264-ABC.mkv",
            )
            self._make(director, "星际穿越.Interstellar.2014.1080p.BluRay.x264-ABC.nfo")
            self._make(director, "星际穿越.Interstellar.2014.1080p.BluRay.x264-ABC.chs.srt")

            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("ACTION_REQUIRED", bundle["status"])
            self.assertEqual("orphan", bundle["source_shape"])
            self.assertEqual(
                "星际穿越.Interstellar.2014.1080p.BluRay.x264-ABC",
                bundle["expected_movie_dir"],
            )
            self._apply(plan, root)
            expected_dir = director / bundle["expected_movie_dir"]
            self.assertTrue(expected_dir.exists())
            # The orphan movie folder stays inside the director scope.
            self.assertEqual(expected_dir.parent, director)
            self.assertFalse(video.exists())
            self.assertTrue(Path(bundle["expected_video_target"]).exists())

    def test_orphan_video_no_chinese_source_is_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            director = root / "Orphan Director"
            video = self._make(director, "NoChineseTitle.2020.1080p.WEB-DL.x264-AAA.mkv")

            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("EXCEPTION", bundle["status"])
            self.assertIn("chinese", bundle["exception"].lower())
            result = self._apply(plan, root)
            self.assertEqual("PASS", result["status"])
            self.assertFalse((root / "NoChineseTitle.NoChineseTitle.2020").exists())
            self.assertTrue(video.exists())

    def test_plan_allows_no_nfo_standard_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "规范电影.NoNFO.2022"
            self._make(src_dir, "NoNFO.2022.1080p.BluRay.x264-AAA.mkv")
            plan = self._plan(root)
            bundle = self._find_bundle(plan, "NoNFO.2022.1080p.BluRay.x264-AAA")
            self.assertIn(bundle["status"], {"ACTION_REQUIRED", "NAMING_PASS"})

    def test_task_root_outside_plan_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root = root.resolve()
            outside = Path(tempfile.mkdtemp())
            foreign = outside / "foreign.mkv"
            foreign.write_text("x")
            plan = {
                "task_root": str(root),
                "version": "1.3.3",
                "bundles": [
                    {
                        "status": "ACTION_REQUIRED",
                        "source_shape": "standard",
                        "source_movie_dir": str(root / "tmp"),
                        "expected_movie_dir": "tmp",
                        "actions": [
                            {
                                "type": "move_file",
                                "source": str(foreign),
                                "target": str(root / "tmp" / foreign.name),
                            }
                        ],
                    }
                ],
            }
            result = self._apply(plan, root)
            self.assertEqual("FAIL", result["status"])
            self.assertIn("outside task root", result["error_summary"])
            self.assertTrue(foreign.exists())

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文.dryrun.2019"
            video = self._make(src_dir, "dry run.2019.1080p.BluRay.x264-AAA.mkv")
            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("ACTION_REQUIRED", bundle["status"])
            result = self._apply(plan, root, dry_run=True)
            self.assertEqual("PASS", result["status"])
            self.assertTrue(src_dir.exists())
            self.assertFalse((root / bundle["expected_movie_dir"]).exists())

    def test_apply_then_second_run_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "影迷.The.Dot.Movie.2019"
            self._make(src_dir, "The.Dot.Movie.2019.1080p.BluRay.x264-GRP.mkv")
            plan = self._plan(root)
            self._apply(plan, root)
            rerun = self._plan(root)
            action_required = [item for item in rerun["bundles"] if item["status"] == "ACTION_REQUIRED"]
            self.assertEqual(0, len(action_required))

    def test_apply_verification_and_no_delete_primitives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文确认.abc.2018"
            video = self._make(src_dir, "abc.2018.720p.WEB-DL.x264-AAA.mkv")
            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            apply_result = self._apply(plan, root)
            verify_result = self._verify(plan, root)
            self.assertEqual("PASS", verify_result["status"])
            self.assertEqual(apply_result["status"], "PASS")
            self.assertTrue((root / bundle["expected_movie_dir"] / video.name).exists())

        source = Path(SCRIPT_PATH)
        for token in ("os.remove(", "rmdir(", ".unlink(", "shutil.rmtree"):
            with self.subTest(token=token):
                self.assertNotIn(token, source.read_text(encoding="utf-8"))

    def test_standard_rename_does_not_leave_old_empty_movie_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "魔鬼的陷阱.Dablova past.1962"
            video = self._make(src_dir, "Dablova past.1962.720p.HDTV.x264-DON.mkv")
            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("ACTION_REQUIRED", bundle["status"])
            result = self._apply(plan, root)
            self.assertEqual("PASS", result["status"])
            self.assertFalse(src_dir.exists(), "old non-conforming folder must be renamed away")
            self.assertTrue((root / bundle["expected_movie_dir"]).is_dir())

    def test_orphan_nfo_xml_title_is_clean_chinese_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            director = root / "Director"
            video = self._make(director, "The.Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            self._make(
                director,
                "The.Movie.2020.1080p.WEB-DL.x264-RLS.nfo",
                "<movie><title>中文片名</title><originaltitle>The Movie</originaltitle></movie>".encode(),
            )
            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("ACTION_REQUIRED", bundle["status"])
            self.assertEqual("中文片名.The Movie.2020.1080p.WEB-DL.x264-RLS", bundle["expected_movie_dir"])

    def test_action_schema_has_preconditions_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文片.The.Movie.2020"
            self._make(src_dir, "The.Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            plan = self._plan(root)
            bundle = self._find_bundle(plan, "The.Movie.2020.1080p.WEB-DL.x264-RLS")
            self.assertEqual("ACTION_REQUIRED", bundle["status"])
            self.assertTrue(bundle["actions"])
            for action in bundle["actions"]:
                self.assertIn("id", action)
                self.assertIn("action", action)
                self.assertIn("target", action)
                self.assertIn("evidence", action)
                self.assertIn("rollback", action)
                self.assertIn("preconditions", action)
                self.assertIn("postconditions", action)

    def test_root_level_orphan_is_exception_without_out_of_scope_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = self._make(root, "孤立片.Interstellar.2014.1080p.BluRay.x264-RLS.mkv")
            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("EXCEPTION", bundle["status"])
            self.assertIn("scope", bundle["exception"].lower())
            result = self._apply(plan, root)
            self.assertEqual("PASS", result["status"])
            self.assertTrue(video.exists())

    def test_conflicting_nfo_and_filename_chinese_sources_are_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            director = root / "Director"
            video = self._make(director, "星际穿越.Interstellar.2014.1080p.BluRay.x264-RLS.mkv")
            self._make(
                director,
                "星际穿越.Interstellar.2014.1080p.BluRay.x264-RLS.nfo",
                "<movie><title>另一个片名</title></movie>".encode(),
            )
            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("EXCEPTION", bundle["status"])
            self.assertIn("conflict", bundle["exception"].lower())
            self.assertTrue(video.exists())

    def test_two_units_planning_same_destination_are_both_exceptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "中文片.Movie.2020"
            second = root / "中文片.Movie.2020.old"
            self._make(first, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            self._make(second, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            plan = self._plan(root)
            bundles = [
                item for item in plan["bundles"]
                if Path(item["source_movie_dir"]).name in {first.name, second.name}
            ]
            self.assertEqual(len(bundles), 2)
            self.assertTrue(all(item["status"] == "EXCEPTION" for item in bundles))
            self.assertTrue(all("collision" in item["exception"].lower() for item in bundles))
            result = self._apply(plan, root)
            self.assertEqual("PASS", result["status"])
            self.assertTrue((first / "Movie.2020.1080p.WEB-DL.x264-RLS.mkv").exists())
            self.assertTrue((second / "Movie.2020.1080p.WEB-DL.x264-RLS.mkv").exists())

    def test_case_only_target_name_is_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文片.Movie.2020.1080p.WEB-DL.x264-RLS"
            self._make(src_dir, "movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            plan = self._plan(root)
            bundle = self._find_bundle(plan, "movie.2020.1080p.WEB-DL.x264-RLS")
            self.assertEqual("EXCEPTION", bundle["status"])
            self.assertTrue(
                "collision" in bundle["exception"].lower()
                or "target" in bundle["exception"].lower()
            )
            self.assertTrue((src_dir / "movie.2020.1080p.WEB-DL.x264-RLS.mkv").exists())

    def test_tampered_plan_hash_is_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文片.Movie.2020"
            video = self._make(src_dir, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            plan = self._plan(root)
            plan["bundles"][0]["expected_movie_dir"] = "恶意目标"
            result = self._apply(plan, root)
            self.assertEqual("FAIL", result["status"])
            self.assertIn("hash", result["error_summary"])
            self.assertTrue(video.exists())

    def test_standard_folder_with_nested_container_is_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文片.Movie.2020"
            self._make(src_dir, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            (src_dir / "BDMV" / "STREAM").mkdir(parents=True)
            self._make(src_dir, "BDMV/STREAM/00001.m2ts")
            plan = self._plan(root)
            bundle = next(
                item
                for item in plan["bundles"]
                if Path(item["source_movie_dir"]).resolve() == src_dir.resolve()
            )
            self.assertEqual("EXCEPTION", bundle["status"])
            self.assertIn("container", bundle["exception"].lower())
            self.assertTrue((src_dir / "Movie.2020.1080p.WEB-DL.x264-RLS.mkv").exists())

    def test_standard_folder_conflicting_video_chinese_prefix_is_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文片.Movie.2020"
            video = self._make(src_dir, "另一片.Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("EXCEPTION", bundle["status"])
            self.assertIn("conflicting", bundle["exception"].lower())
            self.assertTrue(video.exists())

    def test_unrelated_nfo_or_subtitle_is_exception_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文片.Movie.2020"
            video = self._make(src_dir, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            self._make(src_dir, "OtherMovie.nfo", "<movie><title>别的片</title></movie>".encode())
            self._make(src_dir, "OtherMovie.chs.srt")
            plan = self._plan(root)
            bundle = self._find_bundle(plan, video.stem)
            self.assertEqual("EXCEPTION", bundle["status"])
            self.assertIn("unrelated", bundle["exception"].lower())
            self.assertFalse(bundle["actions"])
            self.assertTrue(video.exists())

    def test_cli_apply_and_verify_persist_recovery_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文片.Movie.2020"
            self._make(src_dir, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            script = str(SCRIPT_PATH)
            plan_output = subprocess.run(
                [sys.executable, script, "plan", "--task-root", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            plan_summary = json.loads(plan_output.stdout)
            plan_path = plan_summary["plan_path"]
            dry_run_output = subprocess.run(
                [
                    sys.executable,
                    script,
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
            dry_run_summary = json.loads(dry_run_output.stdout)
            dry_run_record = json.loads(Path(dry_run_summary["result_path"]).read_text())
            self.assertEqual("apply", dry_run_record["mode"])
            self.assertTrue(dry_run_record["dry_run"])
            self.assertEqual(plan_summary["plan_hash"], dry_run_record["plan_hash"])
            self.assertEqual("PASS", dry_run_record["status"])
            apply_output = subprocess.run(
                [sys.executable, script, "apply", "--task-root", str(root), "--plan", plan_path],
                check=True,
                capture_output=True,
                text=True,
            )
            apply_summary = json.loads(apply_output.stdout)
            apply_record = Path(apply_summary["result_path"])
            self.assertTrue(apply_record.is_file())
            self.assertEqual("apply", json.loads(apply_record.read_text())["mode"])
            self.assertEqual(plan_summary["plan_hash"], json.loads(apply_record.read_text())["plan_hash"])
            verify_output = subprocess.run(
                [sys.executable, script, "verify", "--task-root", str(root), "--plan", plan_path],
                check=True,
                capture_output=True,
                text=True,
            )
            verify_summary = json.loads(verify_output.stdout)
            verify_record = Path(verify_summary["result_path"])
            self.assertTrue(verify_record.is_file())
            self.assertEqual("verify", json.loads(verify_record.read_text())["mode"])
            self.assertTrue(verify_summary["naming_plan_only"])
            self.assertNotIn("allowed_completion_message", verify_summary)

    def test_cli_apply_and_verify_require_explicit_plan(self):
        for mode in ("apply", "verify"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                src_dir = root / "中文片.Movie.2020"
                video = self._make(src_dir, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
                process = subprocess.run(
                    [sys.executable, str(SCRIPT_PATH), mode, "--task-root", str(root)],
                    capture_output=True,
                    text=True,
                )
                result = json.loads(process.stdout)
                self.assertNotEqual(0, process.returncode)
                self.assertEqual("FAIL", result["status"])
                self.assertIn("plan", result["error_summary"].lower())
                self.assertTrue(video.exists())

    def test_cli_formal_apply_requires_successful_dry_run_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文片.Movie.2020"
            video = self._make(src_dir, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            plan_output = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "plan", "--task-root", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            plan_path = json.loads(plan_output.stdout)["plan_path"]

            process = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "apply", "--task-root", str(root), "--plan", plan_path],
                capture_output=True,
                text=True,
            )
            result = json.loads(process.stdout)
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", result["status"])
            self.assertEqual(0, result["executed_actions"])
            self.assertIn("dry-run", result["error_summary"].lower())
            self.assertTrue(video.exists())

    def test_cli_rejects_external_tampered_plan_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external_tmp:
            root = Path(tmp)
            external = Path(external_tmp)
            src_dir = root / "中文片.Movie.2020"
            video = self._make(src_dir, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            plan = self._plan(root)
            plan_data = json.loads(Path(plan["plan_path"]).read_text(encoding="utf-8"))
            plan_data["bundles"][0]["actions"][0]["target"] = str(root / "恶意目标")
            plan_data["plan_hash"] = preprocessor._plan_signature(plan_data["bundles"])
            outside_plan = external / "plan.json"
            outside_plan.write_text(json.dumps(plan_data, ensure_ascii=False), encoding="utf-8")

            process = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "apply",
                    "--task-root",
                    str(root),
                    "--plan",
                    str(outside_plan),
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
            )
            result = json.loads(process.stdout)
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", result["status"])
            self.assertEqual(0, result["executed_actions"])
            self.assertTrue(video.exists())

    def test_cli_rejects_plan_reached_through_symlinked_recovery_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            src_dir = root / "中文片.Movie.2020"
            video = self._make(src_dir, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            plan = self._plan(root)
            recovery = root / preprocessor.WORK_RECORD_DIR / "recovery"
            outside_recovery = root / "alternate-recovery"
            outside_recovery.mkdir()
            linked_dir = recovery / "linked"
            os.symlink(str(outside_recovery), str(linked_dir), target_is_directory=True)
            linked_plan = outside_recovery / "linked-plan.json"
            plan_data = json.loads(Path(plan["plan_path"]).read_text(encoding="utf-8"))
            plan_data["plan_path"] = str(linked_plan)
            linked_plan.write_text(json.dumps(plan_data, ensure_ascii=False), encoding="utf-8")
            supplied_plan = linked_dir / linked_plan.name

            process = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "apply",
                    "--task-root",
                    str(root),
                    "--plan",
                    str(supplied_plan),
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
            )
            result = json.loads(process.stdout)
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", result["status"])
            self.assertEqual(0, result["executed_actions"])
            self.assertTrue(video.exists())

    def test_plan_collision_uses_parent_and_casefolded_nfc_name_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "中文片 Movie (2020)"
            second = root / "中文片 Movie [alt] (2020)"
            self._make(first, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            self._make(second, "movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            plan = self._plan(root)
            bundles = [
                item for item in plan["bundles"]
                if Path(item["source_movie_dir"]).name in {first.name, second.name}
            ]
            self.assertEqual(2, len(bundles))
            self.assertTrue(all(item["status"] == "EXCEPTION" for item in bundles))
            self.assertTrue(all("collision" in item["exception"].lower() for item in bundles))
            self.assertTrue((first / "Movie.2020.1080p.WEB-DL.x264-RLS.mkv").exists())
            self.assertTrue((second / "movie.2020.1080p.WEB-DL.x264-RLS.mkv").exists())

    def test_missing_plan_hash_is_rejected_by_apply_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "中文片.Movie.2020"
            video = self._make(src_dir, "Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            plan = self._plan(root)
            plan.pop("plan_hash")
            apply_result = self._apply(plan, root)
            self.assertEqual("FAIL", apply_result["status"])
            self.assertIn("hash", apply_result["error_summary"])
            verify_result = self._verify(plan, root)
            self.assertEqual("FAIL", verify_result["status"])
            self.assertIn("hash", verify_result["error_summary"])
            self.assertTrue(video.exists())

    def test_plan_integrity_requires_current_naming_contract_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = self._make(
                root / "中文片.Movie.2020",
                "Movie.2020.1080p.WEB-DL.x264-RLS.mkv",
            )
            plan = self._plan(root)
            plan["naming_contract_sha256"] = "tampered"

            apply_result = self._apply(plan, root, dry_run=True)
            verify_result = self._verify(plan, root)

            self.assertEqual("FAIL", apply_result["status"])
            self.assertIn("naming", apply_result["error_summary"].lower())
            self.assertEqual("FAIL", verify_result["status"])
            self.assertIn("naming", verify_result["error_summary"].lower())
            self.assertTrue(video.exists())


if __name__ == "__main__":
    unittest.main()
