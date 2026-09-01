import json
import importlib.util
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "movie-organizing"
NFO_SCRIPT = SKILL_DIR / "scripts" / "movie_organizing_nfo.py"

_SPEC = importlib.util.spec_from_file_location("movie_organizing_nfo_test_module", NFO_SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("movie_organizing_nfo.py not found")
NFO = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(NFO)


class MovieOrganizingNfoTest(unittest.TestCase):
    def _make(self, root: Path, relative: str, content: bytes = b"video") -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _fixture(self, root: Path) -> tuple[Path, Path]:
        movie = root / "捷克导演 Frantisek Vlacil" / (
            "是魔鬼的陷阱.Dablova past.1962.720p.HDTV.x264-DON"
        )
        video = self._make(movie, "Dablova past.1962.720p.HDTV.x264-DON.mkv")
        return movie, video

    def _api(self, path: str, params: dict) -> dict:
        if path == "/search/movie":
            return {
                "results": [
                    {
                        "id": 1962,
                        "title": "The Devil's Trap",
                        "original_title": "Ďáblova past",
                        "release_date": "1962-01-01",
                    }
                ]
            }
        if path in {"/movie/1962", "/movie/1963"}:
            return {
                "id": int(path.rsplit("/", 1)[1]),
                "title": "The Devil's Trap",
                "original_title": "Ďáblova past",
                "release_date": "1962-01-01",
                "runtime": 85,
                "overview": "A film.",
            }
        if path in {"/movie/1962/alternative_titles", "/movie/1963/alternative_titles"}:
            return {"titles": [{"title": "Dablova past"}]}
        if path in {"/movie/1962/credits", "/movie/1963/credits"}:
            return {"crew": [{"job": "Director", "name": "František Vláčil"}]}
        if path in {"/movie/1962/external_ids", "/movie/1963/external_ids"}:
            return {"imdb_id": "tt0055910" if path.startswith("/movie/1962") else "tt0055911"}
        raise AssertionError(path)

    def test_unique_database_match_stages_and_atomically_creates_same_stem_nfo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie, video = self._fixture(root)
            with mock.patch.object(NFO, "_tmdb_request", side_effect=self._api), mock.patch.object(
                NFO, "_probe_runtime", return_value=85
            ):
                plan = NFO.make_plan(root)
            entry = plan["entries"][0]
            self.assertEqual("AUTO_CREATE", entry["status"])
            self.assertEqual(1962, entry["tmdb_id"])
            self.assertEqual("tt0055910", entry["imdb_id"])
            self.assertTrue(Path(entry["staging_path"]).is_file())
            self.assertEqual(video.with_suffix(".nfo").resolve(), Path(entry["target_path"]))
            self.assertNotIn("api_key", json.dumps(plan))

            dry = NFO.apply_plan(plan, root, dry_run=True)
            self.assertEqual("PASS", dry["status"])
            self.assertFalse(video.with_suffix(".nfo").exists())

            applied = NFO.apply_plan(plan, root)
            self.assertEqual("PASS", applied["status"])
            verified = NFO.verify_plan(plan, root)
            self.assertEqual("PASS", verified["status"])
            document = ET.parse(video.with_suffix(".nfo"))
            self.assertEqual("1962", document.findtext("./uniqueid[@type='tmdb']"))
            self.assertEqual("tt0055910", document.findtext("./uniqueid[@type='imdb']"))
            self.assertEqual("Ďáblova past", document.findtext("originaltitle"))
            self.assertEqual("85", document.findtext("runtime"))

    def test_ambiguous_or_network_failure_never_writes_nfo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _movie, video = self._fixture(root)

            def ambiguous(path: str, params: dict) -> dict:
                value = self._api(path, params)
                if path == "/search/movie":
                    value["results"].append(dict(value["results"][0], id=1963))
                return value

            with mock.patch.object(NFO, "_tmdb_request", side_effect=ambiguous), mock.patch.object(
                NFO, "_probe_runtime", return_value=85
            ):
                plan = NFO.make_plan(root)
            self.assertEqual("PENDING_AMBIGUOUS", plan["entries"][0]["status"])
            self.assertFalse(video.with_suffix(".nfo").exists())

            with mock.patch.object(NFO, "_tmdb_request", side_effect=NFO.NfoApiError("offline")), mock.patch.object(
                NFO, "_probe_runtime", return_value=85
            ):
                blocked = NFO.make_plan(root)
            self.assertEqual("PENDING_API", blocked["entries"][0]["status"])
            self.assertFalse(video.with_suffix(".nfo").exists())

    def test_pending_identity_isolation_moves_complete_movie_unit_under_task_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie, video = self._fixture(root)

            def ambiguous(path: str, params: dict) -> dict:
                value = self._api(path, params)
                if path == "/search/movie":
                    value["results"].append(dict(value["results"][0], id=1963))
                return value

            with mock.patch.object(NFO, "_tmdb_request", side_effect=ambiguous), mock.patch.object(
                NFO, "_probe_runtime", return_value=85
            ):
                plan = NFO.make_plan(root)
            self.assertEqual("PENDING_AMBIGUOUS", plan["entries"][0]["status"])
            self.assertEqual(1, plan["counts"]["pending_isolation"])
            action = plan["pending_actions"][0]
            pending_target = Path(action["target"])
            self.assertEqual(
                root.resolve() / NFO.PENDING_DIR / movie.parent.name / movie.name,
                pending_target,
            )
            self.assertIn("rollback", action)

            dry = NFO.apply_plan(plan, root, dry_run=True)
            self.assertEqual("PASS", dry["status"])
            self.assertEqual(1, dry["pending_isolation_planned"])
            self.assertTrue(movie.is_dir())
            applied = NFO.apply_plan(plan, root)
            self.assertEqual("PASS", applied["status"])
            self.assertEqual(1, applied["pending_isolation_count"])
            self.assertFalse(movie.exists())
            self.assertTrue(pending_target.is_dir())
            self.assertTrue((pending_target / video.name).is_file())

            verified = NFO.verify_plan(plan, root)
            self.assertEqual("PASS", verified["status"])
            self.assertEqual(1, verified["pending_count"])
            self.assertEqual(1, verified["pending_isolation_count"])

    def test_pending_isolation_target_collision_blocks_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie, _video = self._fixture(root)
            existing = root / NFO.PENDING_DIR / movie.parent.name / movie.name
            existing.mkdir(parents=True)
            with mock.patch.object(NFO, "_tmdb_request", side_effect=NFO.NfoApiError("offline")), mock.patch.object(
                NFO, "_probe_runtime", return_value=85
            ):
                plan = NFO.make_plan(root)
            self.assertEqual("PENDING_API", plan["entries"][0]["status"])
            self.assertEqual(0, plan["counts"]["pending_isolation"])
            self.assertEqual(1, plan["counts"]["pending_isolation_blocked"])
            self.assertEqual("BLOCKED", plan["entries"][0]["pending_isolation_status"])
            self.assertTrue(movie.is_dir())
            self.assertEqual([], list(existing.iterdir()))

    def test_nfo_rollback_uses_recoverable_moves_not_destructive_directory_cleanup(self):
        source = NFO_SCRIPT.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\.(?:unlink|rmdir)\s*\(", source))
        self.assertNotIn("shutil.rmtree", source)

    def test_existing_valid_nfo_is_never_overwritten_and_wrong_nfo_is_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _movie, video = self._fixture(root)
            nfo = video.with_suffix(".nfo")
            original = (
                "<movie><title>手工标题</title><originaltitle>Ďáblova past</originaltitle>"
                "<year>1962</year><uniqueid type=\"tmdb\" default=\"true\">1962</uniqueid></movie>"
            ).encode()
            nfo.write_bytes(original)
            with mock.patch.object(NFO, "_tmdb_request", side_effect=self._api) as request:
                plan = NFO.make_plan(root)
            self.assertEqual("KEEP_EXISTING", plan["entries"][0]["status"])
            self.assertEqual(original, nfo.read_bytes())
            self.assertTrue(request.call_count >= 2)

            nfo.write_text("<movie><year>1999</year></movie>", encoding="utf-8")
            with mock.patch.object(NFO, "_tmdb_request", side_effect=self._api) as request:
                conflict = NFO.make_plan(root)
            self.assertEqual("PENDING_EXISTING_NFO", conflict["entries"][0]["status"])
            self.assertEqual("1999", ET.parse(nfo).findtext("year"))
            request.assert_not_called()

    def test_identity_lock_is_required_by_audit_and_is_created_after_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _movie, video = self._fixture(root)
            nfo = video.with_suffix(".nfo")
            nfo.write_text(
                "<movie><title>是魔鬼的陷阱</title><originaltitle>Ďáblova past</originaltitle>"
                "<year>1962</year><uniqueid type=\"tmdb\">1962</uniqueid></movie>",
                encoding="utf-8",
            )
            with mock.patch.object(NFO, "_tmdb_request", side_effect=self._api):
                plan = NFO.make_plan(root)
            self.assertEqual("KEEP_EXISTING", plan["entries"][0]["status"])
            before_lock = NFO.audit_nfo_tree(root)
            self.assertEqual("FAIL", before_lock["status"])
            self.assertEqual(1, before_lock["counts"]["active_nfo_identity_unverified"])
            self.assertEqual("PASS", NFO.apply_plan(plan, root, dry_run=True)["status"])
            self.assertEqual("PASS", NFO.apply_plan(plan, root)["status"])
            verified = NFO.verify_plan(plan, root)
            self.assertEqual("PASS", verified["status"])
            lock = NFO._write_identity_lock(root, plan, verified)
            self.assertTrue(lock.is_file())
            after_lock = NFO.audit_nfo_tree(root)
            self.assertEqual("PASS", after_lock["status"])

    def test_staging_symlink_is_rejected_before_any_nfo_write(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            self._fixture(root)
            work = root / "_work-record_"
            work.mkdir()
            (work / "recovery").mkdir()
            (work / "nfo-staging").symlink_to(Path(outside), target_is_directory=True)
            with mock.patch.object(NFO, "_tmdb_request", side_effect=self._api), mock.patch.object(
                NFO, "_probe_runtime", return_value=85
            ):
                with self.assertRaises(NFO.NfoPlanError):
                    NFO.make_plan(root)
            self.assertEqual([], list(Path(outside).iterdir()))

    def test_large_library_plan_limits_batch_to_one_director_and_ten_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for director_index in range(4):
                director = root / f"导演{director_index} Director{director_index}"
                for index in range(6):
                    folder = director / f"片{director_index}-{index}.Movie{director_index}-{index}.2020"
                    self._make(folder, f"Movie{director_index}-{index}.2020.1080p.BluRay.x264-RLS.mkv")
            # This test exercises the preprocessor metadata imported by the NFO plan.
            with mock.patch.object(NFO, "_tmdb_request", side_effect=NFO.NfoApiError("offline")):
                plan = NFO.make_plan(root)
            self.assertTrue(plan["large_library_mode"])
            self.assertLessEqual(plan["counts"]["selected_units"], 10)
            self.assertLessEqual(len({entry["batch_director"] for entry in plan["entries"] if entry.get("selected")}), 1)

    def test_large_nfo_plan_advances_past_identity_locked_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            director = root / "导演 Director"
            locked_names = set()
            for index in range(22):
                movie = director / f"片{index}.Movie{index}.2020.1080p.BluRay.x264-RLS"
                video = self._make(movie, f"Movie{index}.2020.1080p.BluRay.x264-RLS.mkv")
                if index < 10:
                    video.with_suffix(".nfo").write_text(
                        f'<movie><uniqueid type="tmdb">{index + 1}</uniqueid></movie>',
                        encoding="utf-8",
                    )
                    locked_names.add(video.name)

            def locked(root_path, video, nfo, tmdb_id):
                return Path(video).name in locked_names

            with mock.patch.object(NFO, "_lock_matches", side_effect=locked), mock.patch.object(
                NFO, "_tmdb_request", side_effect=NFO.NfoApiError("offline")
            ), mock.patch.object(NFO, "_probe_runtime", return_value=85):
                plan = NFO.make_plan(root)

            selected = [entry for entry in plan["entries"] if entry.get("selected")]
            self.assertTrue(plan["large_library_mode"])
            self.assertEqual(10, len(selected))
            self.assertTrue(all(Path(entry["source_video"]).name not in locked_names for entry in selected))
            self.assertTrue(all(entry["status"] == "PENDING_API" for entry in selected))

    def test_all_identity_locked_large_plan_has_no_false_deferred_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            director = root / "导演 Director"
            for index in range(21):
                movie = director / f"片{index}.Movie{index}.2020.1080p.BluRay.x264-RLS"
                video = self._make(movie, f"Movie{index}.2020.1080p.BluRay.x264-RLS.mkv")
                video.with_suffix(".nfo").write_text(
                    f'<movie><uniqueid type="tmdb">{index + 1}</uniqueid></movie>',
                    encoding="utf-8",
                )

            with mock.patch.object(NFO, "_lock_matches", return_value=True), mock.patch.object(
                NFO, "_tmdb_request", side_effect=AssertionError("locked identities must not query again")
            ):
                plan = NFO.make_plan(root)

            self.assertTrue(plan["large_library_mode"])
            self.assertEqual(0, plan["counts"]["selected_units"])
            self.assertEqual(0, plan["counts"]["deferred"])
            self.assertEqual(21, plan["counts"]["keep_existing"])


if __name__ == "__main__":
    unittest.main()
