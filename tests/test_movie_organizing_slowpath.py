"""RED contract tests for the v1.3.5 movie-organizing slow channel.

The slow channel is deliberately tested through its CLI boundary.  Fixtures
are temporary directories and the audit reports are produced by the existing
read-only audit script; no real media tree is touched.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "movie-organizing"
SLOWPATH_SCRIPT = SKILL_DIR / "scripts" / "movie_organizing_slowpath.py"
AUDIT_SCRIPT = SKILL_DIR / "scripts" / "movie_organizing_audit.py"

_AUDIT_SPEC = importlib.util.spec_from_file_location(
    "movie_organizing_slowpath_audit", AUDIT_SCRIPT
)
if _AUDIT_SPEC is None or _AUDIT_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("movie_organizing_audit.py not found")
AUDIT_MODULE = importlib.util.module_from_spec(_AUDIT_SPEC)
_AUDIT_SPEC.loader.exec_module(AUDIT_MODULE)

_SLOWPATH_SPEC = importlib.util.spec_from_file_location(
    "movie_organizing_slowpath_module", SLOWPATH_SCRIPT
)
if _SLOWPATH_SPEC is None or _SLOWPATH_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("movie_organizing_slowpath.py not found")
SLOWPATH_MODULE = importlib.util.module_from_spec(_SLOWPATH_SPEC)
_SLOWPATH_SPEC.loader.exec_module(SLOWPATH_MODULE)


class MovieOrganizingSlowpathTest(unittest.TestCase):
    """The agent may submit semantic decisions, never a hand-written plan."""

    def _make(self, root: Path, relative: str, content: bytes = b"x") -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _fresh_audit(self, root: Path) -> tuple[Path, dict]:
        report, exit_code = AUDIT_MODULE.audit_task_root(root)
        self.assertTrue(report.get("report_path"), report)
        self.assertTrue(Path(report["report_path"]).is_file(), report)
        self.assertEqual(report["status"], "PASS" if exit_code == 0 else "FAIL")
        return Path(report["report_path"]), report

    def _run(self, mode: str, root: Path, *arguments: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        self.assertTrue(
            SLOWPATH_SCRIPT.is_file(),
            "movie_organizing_slowpath.py is required for the v1.3.5 slow channel",
        )
        process = subprocess.run(
            [
                sys.executable,
                str(SLOWPATH_SCRIPT),
                mode,
                "--task-root",
                str(root),
                *arguments,
            ],
            capture_output=True,
            text=True,
        )
        self.assertTrue(
            process.stdout.strip(),
            f"slowpath {mode} emitted no JSON (rc={process.returncode}): {process.stderr}",
        )
        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - useful RED output
            self.fail(f"slowpath {mode} emitted invalid JSON: {process.stdout}: {exc}")
        return process, payload

    def _write_json(self, path: Path, payload: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def _template(self, root: Path, audit_path: Path, phase: str) -> tuple[dict, Path]:
        _process, payload = self._run(
            "template",
            root,
            "--audit",
            str(audit_path),
            "--phase",
            phase,
        )
        self.assertEqual("PASS", payload.get("status"), payload)
        template_path = Path(payload["template_path"])
        self.assertTrue(template_path.is_file(), payload)
        return json.loads(template_path.read_text(encoding="utf-8")), template_path

    def _decisions(
        self,
        root: Path,
        template: dict,
        decision: str,
        *,
        index: int = 0,
        extra: dict | None = None,
        name: str = "decisions.json",
    ) -> Path:
        item = template["items"][index]
        decision_item = {
            "candidate_id": item["candidate_id"],
            "decision": decision,
            **(extra or {}),
        }
        if decision == "pending_isolation" and not {"reason", "evidence"}.intersection(decision_item):
            decision_item["reason"] = "isolate unresolved candidate pending manual confirmation"
        if decision == "rehome_unit" and "evidence" not in decision_item:
            decision_item["evidence"] = "resolved from selected candidate video and naming facts"
        value = {
            "schema": "movie-organizing-slowpath/decisions/v1",
            "phase": template["phase"],
            "items": [decision_item],
        }
        return self._write_json(root / "_work-record_" / "recovery" / name, value)

    def _plan(
        self,
        root: Path,
        audit_path: Path,
        template_path: Path,
        decisions_path: Path,
    ) -> tuple[dict, Path]:
        _process, payload = self._run(
            "plan",
            root,
            "--audit",
            str(audit_path),
            "--template",
            str(template_path),
            "--decisions",
            str(decisions_path),
        )
        self.assertEqual("PASS", payload.get("status"), payload)
        plan_path = Path(payload["plan_path"])
        self.assertTrue(plan_path.is_file(), payload)
        return json.loads(plan_path.read_text(encoding="utf-8")), plan_path

    def _make_core_exception_units(self, root: Path, count: int) -> None:
        for index in range(count):
            self._make(
                root,
                f"导演 Director/wrapper-{index}/NoChinese{index}.Movie.2020.1080p.WEB-DL.x264-RLS/"
                f"NoChinese{index}.Movie.2020.1080p.WEB-DL.x264-RLS.mkv",
            )

    def _make_pending_fixture(self, root: Path) -> Path:
        return self._make(
            root,
            "导演 Director/wrapper/legacy/NoChinese.Movie.2020.1080p.WEB-DL.x264-RLS/"
            "NoChinese.Movie.2020.1080p.WEB-DL.x264-RLS.mkv",
        )

    def _make_rehome_fixture(self, root: Path) -> tuple[Path, Path]:
        video = self._make(
            root,
            "导演 Director/wrapper/legacy/中文前缀.Prefix.Movie.2021.1080p.WEB-DL.x264-RLS.mkv",
        )
        subtitle = self._make(
            root,
            "导演 Director/wrapper/legacy/中文前缀.Prefix.Movie.2021.1080p.WEB-DL.x264-RLS.chs.srt",
        )
        return video, subtitle

    def _make_duplicate_fixture(self, root: Path) -> tuple[Path, Path]:
        first = self._make(
            root,
            "导演 Director/同片.Movie.2020.720p.WEB-DL.x264-LOW/Movie.2020.720p.WEB-DL.x264-LOW.mkv",
        )
        second = self._make(
            root,
            "导演 Director/同片.Movie.2020.1080p.BluRay.x264-HIGH/Movie.2020.1080p.BluRay.x264-HIGH.mkv",
        )
        return first, second

    def _make_wrong_director_exception_fixture(self, root: Path) -> Path:
        return self._make(
            root,
            "错误导演/旧片名.Old Movie.2020/Old.Movie.2020.1080p.WEB-DL.x264-RLS.mkv",
        )

    def _make_root_orphan_fixture(self, root: Path) -> Path:
        return self._make(root, "Root.Movie.2022.1080p.WEB-DL.x264-RLS.mkv")

    def _make_multi_video_fixture(self, root: Path) -> tuple[Path, Path]:
        first = self._make(
            root,
            "错误导演/合集/First.Movie.2020.1080p.WEB-DL.x264-RLS.mkv",
        )
        second = self._make(
            root,
            "错误导演/合集/Second.Movie.2020.720p.WEB-DL.x264-RLS.mkv",
        )
        return first, second

    def _make_dirty_semantic_rehome_fixture(self, root: Path, kind: str) -> tuple[Path, Path]:
        """Build an EXCEPTION candidate that semantic rehome must not partially move."""

        container = root / "错误导演" / {
            "unknown_file": "脏容器-未知文件",
            "child_dir": "脏容器-子目录",
            "multi_video": "脏容器-多视频",
        }[kind]
        first = self._make(
            root,
            f"{container.relative_to(root)}/Dirty.Movie.2020.1080p.WEB-DL.x264-RLS.mkv",
        )
        if kind == "unknown_file":
            self._make(root, f"{container.relative_to(root)}/notes.txt")
        elif kind == "child_dir":
            self._make(root, f"{container.relative_to(root)}/nested/extra.txt")
        elif kind == "multi_video":
            self._make(
                root,
                f"{container.relative_to(root)}/Other.Movie.2020.720p.WEB-DL.x264-RLS.mkv",
            )
        else:  # pragma: no cover - callers enumerate the fixture variants
            raise AssertionError(f"unknown dirty fixture kind: {kind}")
        return first, container

    def test_template_extracts_fresh_core_exceptions_and_caps_batch_at_twenty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_core_exception_units(root, count=21)
            audit_path, report = self._fresh_audit(root)
            self.assertEqual("FAIL", report["core_gate"]["status"])

            template, _template_path = self._template(root, audit_path, "core_exception")

            self.assertEqual("core_exception", template["phase"])
            self.assertEqual(str(audit_path), template["audit_path"])
            self.assertEqual(
                hashlib.sha256(audit_path.read_bytes()).hexdigest(),
                template["audit_sha256"],
            )
            self.assertGreater(len(template["items"]), 0)
            self.assertLessEqual(len(template["items"]), 20)
            self.assertTrue(all(item.get("candidate_id") for item in template["items"]))
            self.assertTrue(all(item.get("source") for item in template["items"]))
            unsigned = dict(template)
            declared_hash = unsigned.pop("template_hash")
            unsigned.pop("template_path")
            expected_hash = hashlib.sha256(
                json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            self.assertEqual(expected_hash, declared_hash)

    def test_plan_rejects_more_than_twenty_items_and_audit_hash_or_path_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = self._make_pending_fixture(root)
            audit_path, _report = self._fresh_audit(root)
            template, template_path = self._template(root, audit_path, "core_exception")
            decisions_path = self._decisions(root, template, "pending_isolation")

            over_limit = dict(template)
            over_limit["items"] = list(template["items"]) * 21
            over_limit_path = self._write_json(
                root / "_work-record_" / "recovery" / "template-over-limit.json",
                over_limit,
            )
            process, payload = self._run(
                "plan",
                root,
                "--audit",
                str(audit_path),
                "--template",
                str(over_limit_path),
                "--decisions",
                str(decisions_path),
            )
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertEqual(0, payload.get("planned_actions", 0))
            self.assertTrue(source_video.exists())

            original_audit = audit_path.read_text(encoding="utf-8")
            audit_path.write_text(original_audit + "\n", encoding="utf-8")
            process, payload = self._run(
                "plan",
                root,
                "--audit",
                str(audit_path),
                "--template",
                str(template_path),
                "--decisions",
                str(decisions_path),
            )
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertTrue(source_video.exists())

            drifted_path = root / "_work-record_" / "recovery" / "audit-drifted-path.json"
            shutil.copy2(audit_path, drifted_path)
            process, payload = self._run(
                "plan",
                root,
                "--audit",
                str(drifted_path),
                "--template",
                str(template_path),
                "--decisions",
                str(decisions_path),
            )
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertTrue(source_video.exists())

    def test_plan_rejects_action_source_target_injection_and_missing_candidate_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = self._make_pending_fixture(root)
            audit_path, _report = self._fresh_audit(root)
            template, _template_path = self._template(root, audit_path, "core_exception")
            item = template["items"][0]
            recovery = root / "_work-record_" / "recovery"

            injected = self._write_json(
                recovery / "decisions-injected.json",
                {
                    "schema": "movie-organizing-slowpath/decisions/v1",
                    "phase": "core_exception",
                    "items": [
                        {
                            "candidate_id": item["candidate_id"],
                            "decision": "pending_isolation",
                            "action": "rename_dir",
                            "source": str(source_video.parent),
                            "target": str(root / "outside"),
                        }
                    ],
                },
            )
            process, payload = self._run(
                "plan",
                root,
                "--audit",
                str(audit_path),
                "--template",
                str(_template_path),
                "--decisions",
                str(injected),
            )
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertEqual(0, payload.get("planned_actions", 0))
            self.assertTrue(source_video.exists())

            missing_id = self._write_json(
                recovery / "decisions-missing-id.json",
                {
                    "schema": "movie-organizing-slowpath/decisions/v1",
                    "phase": "core_exception",
                    "items": [{"decision": "pending_isolation"}],
                },
            )
            process, payload = self._run(
                "plan",
                root,
                "--audit",
                str(audit_path),
                "--template",
                str(_template_path),
                "--decisions",
                str(missing_id),
            )
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertTrue(source_video.exists())

    def test_dedupe_keep_is_zero_mutation_when_core_gate_is_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = self._make_duplicate_fixture(root)
            audit_path, report = self._fresh_audit(root)
            self.assertEqual("PASS", report["core_gate"]["status"])
            self.assertTrue(report["dedupe_gate"]["candidate_groups"])

            # Preserve the candidate evidence but make the core gate fail.  A
            # dedupe_keep semantic decision must never become a filesystem
            # mutation while core naming/placement is unresolved.
            bad_report = json.loads(audit_path.read_text(encoding="utf-8"))
            bad_report["core_gate"]["status"] = "FAIL"
            bad_report["core_gate"]["counts"]["active_exception_units"] = 1
            bad_report["status"] = "FAIL"
            bad_report_path = root / "_work-record_" / "recovery" / "audit-core-fail.json"
            bad_report["report_path"] = str(bad_report_path)
            self._write_json(bad_report_path, bad_report)

            template, template_path = self._template(root, bad_report_path, "dedupe")
            self.assertTrue(template["items"])
            decisions_path = self._decisions(
                root,
                template,
                "dedupe_keep",
                extra={
                    "keep_member": template["items"][0]["members"][0],
                    "same_identity": True,
                    "same_edition_cut": True,
                    "quality_evidence": "bad report gate must still block this otherwise complete decision",
                },
            )
            process, payload = self._run(
                "plan",
                root,
                "--audit",
                str(bad_report_path),
                "--template",
                str(template_path),
                "--decisions",
                str(decisions_path),
            )
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertEqual(0, payload.get("planned_actions", 0))
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_rehome_requires_dry_run_then_formal_apply_then_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video, source_subtitle = self._make_rehome_fixture(root)
            audit_path, report = self._fresh_audit(root)
            self.assertEqual("FAIL", report["core_gate"]["status"])
            template, template_path = self._template(root, audit_path, "core_exception")
            decisions_path = self._decisions(root, template, "rehome_unit")
            plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)

            actions = plan.get("actions", [])
            self.assertTrue(actions, plan)
            self.assertTrue(
                all(action.get("action") not in {"move_file", "copy", "delete", "rm"} for action in actions),
                actions,
            )

            # Formal apply before a successful dry-run is forbidden and must
            # leave the source untouched.
            process, payload = self._run("apply", root, "--plan", str(plan_path))
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertEqual(0, payload.get("executed_actions", 0))
            self.assertTrue(source_video.exists())
            self.assertTrue(source_subtitle.exists())

            process, payload = self._run("apply", root, "--plan", str(plan_path), "--dry-run")
            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", payload["status"])
            self.assertTrue(source_video.exists())
            self.assertTrue(source_subtitle.exists())
            self.assertTrue(Path(payload["result_path"]).is_file(), payload)

            process, payload = self._run("verify", root, "--plan", str(plan_path))
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertTrue(source_video.exists())

            process, payload = self._run("apply", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", payload["status"])
            self.assertTrue(Path(payload["result_path"]).is_file(), payload)
            self.assertFalse(source_video.exists())
            self.assertFalse(source_subtitle.exists())

            process, payload = self._run("verify", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", payload["status"])

    def test_template_hash_tampering_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = self._make_pending_fixture(root)
            audit_path, _report = self._fresh_audit(root)
            template, template_path = self._template(root, audit_path, "core_exception")
            decisions_path = self._decisions(root, template, "pending_isolation")

            tampered = dict(template)
            tampered["items"] = [dict(template["items"][0], evidence="tampered evidence")]
            # Keep the declared recovery path unchanged so the failure is
            # specifically the semantic hash gate, not a filename mismatch.
            tampered_path = self._write_json(template_path, tampered)
            process, payload = self._run(
                "plan",
                root,
                "--audit",
                str(audit_path),
                "--template",
                str(tampered_path),
                "--decisions",
                str(decisions_path),
            )
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertIn("template hash", payload.get("error_summary", ""))
            self.assertTrue(source_video.exists())

    def test_plan_action_tampering_is_rejected_even_after_hash_recalculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = self._make_pending_fixture(root)
            audit_path, _report = self._fresh_audit(root)
            template, template_path = self._template(root, audit_path, "core_exception")
            decisions_path = self._decisions(root, template, "pending_isolation")
            _plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)

            tampered = json.loads(plan_path.read_text(encoding="utf-8"))
            rename_action = next(action for action in tampered["actions"] if action["action"] == "rename_path")
            rename_action["target"] = str(root / "tampered-target")
            unsigned = dict(tampered)
            unsigned.pop("plan_hash", None)
            unsigned.pop("plan_path", None)
            tampered["plan_hash"] = hashlib.sha256(
                json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            self._write_json(plan_path, tampered)

            process, payload = self._run("apply", root, "--plan", str(plan_path), "--dry-run")
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertIn("plan semantic field drift", payload.get("error_summary", ""))
            self.assertTrue(source_video.exists())

    def test_core_decisions_require_auditable_reason_or_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = self._make_pending_fixture(root)
            audit_path, _report = self._fresh_audit(root)
            template, template_path = self._template(root, audit_path, "core_exception")
            item = template["items"][0]
            recovery = root / "_work-record_" / "recovery"
            for decision, fields in (
                ("pending_isolation", {}),
                (
                    "rehome_unit",
                    {
                        "resolved_director_name": "导演 Director",
                        "resolved_chinese_title": "片名",
                        "main_video_name": source_video.name,
                    },
                ),
            ):
                decisions_path = self._write_json(
                    recovery / f"decisions-no-evidence-{decision}.json",
                    {
                        "schema": "movie-organizing-slowpath/decisions/v1",
                        "phase": "core_exception",
                        "items": [
                            {"candidate_id": item["candidate_id"], "decision": decision, **fields}
                        ],
                    },
                )
                process, payload = self._run(
                    "plan",
                    root,
                    "--audit",
                    str(audit_path),
                    "--template",
                    str(template_path),
                    "--decisions",
                    str(decisions_path),
                )
                self.assertNotEqual(0, process.returncode)
                self.assertEqual("FAIL", payload["status"])
                self.assertEqual(0, payload.get("planned_actions", 0))
                self.assertTrue(source_video.exists())

    def test_dedupe_decision_requires_identity_edition_and_quality_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _first, _second = self._make_duplicate_fixture(root)
            audit_path, report = self._fresh_audit(root)
            self.assertEqual("PASS", report["core_gate"]["status"])
            template, template_path = self._template(root, audit_path, "dedupe")
            keep = template["items"][0]["members"][0]
            invalid_extras = (
                {"keep_member": keep, "same_edition_cut": True, "quality_evidence": "1080p"},
                {"keep_member": keep, "same_identity": True, "quality_evidence": "1080p"},
                {"keep_member": keep, "same_identity": True, "same_edition_cut": True, "quality_evidence": "  "},
            )
            for index, extra in enumerate(invalid_extras):
                decisions_path = self._decisions(
                    root,
                    template,
                    "dedupe_keep",
                    extra=extra,
                    name=f"decisions-missing-evidence-{index}.json",
                )
                process, payload = self._run(
                    "plan",
                    root,
                    "--audit",
                    str(audit_path),
                    "--template",
                    str(template_path),
                    "--decisions",
                    str(decisions_path),
                )
                self.assertNotEqual(0, process.returncode)
                self.assertEqual("FAIL", payload["status"])
                self.assertEqual(0, payload.get("planned_actions", 0))

    def test_pending_isolation_completes_full_recovery_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = self._make_pending_fixture(root)
            audit_path, _report = self._fresh_audit(root)
            template, template_path = self._template(root, audit_path, "core_exception")
            decisions_path = self._decisions(root, template, "pending_isolation")
            _plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)

            process, payload = self._run("apply", root, "--plan", str(plan_path), "--dry-run")
            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", payload["status"])
            self.assertTrue(source_video.exists())

            process, payload = self._run("apply", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", payload["status"])
            result_record = json.loads(Path(payload["result_path"]).read_text(encoding="utf-8"))
            self.assertTrue(result_record["decision_evidence"][0]["reason"])
            self.assertFalse(source_video.exists())
            pending_dirs = [path for path in (root / "_待确认_").iterdir() if path.is_dir()]
            self.assertEqual(1, len(pending_dirs))
            self.assertTrue(any(path.is_file() for path in pending_dirs[0].iterdir()))

            process, payload = self._run("verify", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", payload["status"])

    def test_dedupe_keep_completes_full_recovery_chain_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = self._make_duplicate_fixture(root)
            audit_path, _report = self._fresh_audit(root)
            template, template_path = self._template(root, audit_path, "dedupe")
            keep = template["items"][0]["members"][0]
            decisions_path = self._decisions(
                root,
                template,
                "dedupe_keep",
                extra={
                    "keep_member": keep,
                    "same_identity": True,
                    "same_edition_cut": True,
                    "quality_evidence": "1080p BluRay is higher quality than 720p WEB-DL",
                    "full_hash_evidence": "distinct full-file hashes recorded",
                    "reason": "same title/year; selected the higher quality edition",
                },
                name="decisions-dedupe-positive.json",
            )
            plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)
            self.assertEqual(True, plan["items"][0]["same_identity"])
            self.assertEqual(True, plan["items"][0]["same_edition_cut"])
            self.assertIn("quality_evidence", plan["items"][0])
            self.assertTrue(any("same_identity" in str(action.get("evidence")) for action in plan["actions"]))

            process, payload = self._run("apply", root, "--plan", str(plan_path), "--dry-run")
            self.assertEqual(0, process.returncode)
            self.assertTrue(first.exists() and second.exists())
            process, payload = self._run("apply", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", payload["status"])
            self.assertTrue(Path(payload["result_path"]).is_file())
            result_record = json.loads(Path(payload["result_path"]).read_text(encoding="utf-8"))
            self.assertEqual(True, result_record["decision_evidence"][0]["same_identity"])
            self.assertIn("quality_evidence", result_record["decision_evidence"][0])
            self.assertTrue(Path(keep).exists())
            loser = first if str(first.parent.resolve()) != str(Path(keep).resolve()) else second
            self.assertFalse(loser.exists())
            self.assertTrue(any(path.name.startswith("_trash_") for path in root.iterdir()))

            process, payload = self._run("verify", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", payload["status"])

    def test_dedupe_pending_completes_full_recovery_chain_without_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = self._make_duplicate_fixture(root)
            audit_path, report = self._fresh_audit(root)
            self.assertEqual("PASS", report["core_gate"]["status"])
            template, template_path = self._template(root, audit_path, "dedupe")
            decisions_path = self._decisions(
                root,
                template,
                "dedupe_pending",
                extra={"reason": "edition and quality evidence cannot uniquely select a winner"},
                name="decisions-dedupe-pending.json",
            )
            _plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)

            process, payload = self._run("apply", root, "--plan", str(plan_path), "--dry-run")
            self.assertEqual(0, process.returncode)
            self.assertTrue(first.exists() and second.exists())
            process, payload = self._run("apply", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            pending_group = root / "_待确认_" / template["items"][0]["candidate_id"]
            self.assertTrue((pending_group / first.parent.name).is_dir())
            self.assertTrue((pending_group / second.parent.name).is_dir())
            process, payload = self._run("verify", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            self.assertEqual("PASS", payload["status"])

    def test_apply_rejects_plan_after_candidate_tree_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = self._make_pending_fixture(root)
            audit_path, _report = self._fresh_audit(root)
            template, template_path = self._template(root, audit_path, "core_exception")
            decisions_path = self._decisions(root, template, "pending_isolation")
            _plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)
            source_container = Path(template["items"][0]["source"])
            drifted = source_container.parent / "drifted-container"
            source_container.rename(drifted)
            process, payload = self._run("apply", root, "--plan", str(plan_path), "--dry-run")
            self.assertNotEqual(0, process.returncode)
            self.assertEqual("FAIL", payload["status"])
            self.assertIn("fresh audit candidate/tree drift", payload.get("error_summary", ""))
            self.assertTrue((drifted / source_video.name).exists())

    def test_rehome_exception_uses_semantic_identity_without_path_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = self._make_wrong_director_exception_fixture(root)
            audit_path, report = self._fresh_audit(root)
            self.assertEqual("FAIL", report["core_gate"]["status"])
            template, template_path = self._template(root, audit_path, "core_exception")
            decisions_path = self._decisions(
                root,
                template,
                "rehome_unit",
                extra={
                    "resolved_director_name": "正确导演 Correct Director",
                    "resolved_chinese_title": "旧片名",
                    "main_video_name": source_video.name,
                },
                name="decisions-semantic-rehome.json",
            )
            _plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)
            process, payload = self._run("apply", root, "--plan", str(plan_path), "--dry-run")
            self.assertEqual(0, process.returncode)
            process, payload = self._run("apply", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            self.assertFalse(source_video.exists())
            result_record = json.loads(Path(payload["result_path"]).read_text(encoding="utf-8"))
            self.assertTrue(result_record["decision_evidence"][0]["evidence"])
            self.assertFalse(source_video.parent.exists())
            target_files = list((root / "正确导演 Correct Director").rglob("*.mkv"))
            self.assertEqual(1, len(target_files))
            process, payload = self._run("verify", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)

            # Rebuild the fixture in a fresh root for the injection check.
            root2 = Path(tempfile.mkdtemp(dir=tmp))
            try:
                injected_source = self._make_wrong_director_exception_fixture(root2)
                audit2, _ = self._fresh_audit(root2)
                template2, template_path2 = self._template(root2, audit2, "core_exception")
                injected = self._decisions(
                    root2,
                    template2,
                    "rehome_unit",
                    extra={
                        "resolved_director_name": "../outside",
                        "resolved_chinese_title": "旧片名",
                        "main_video_name": injected_source.name,
                    },
                    name="decisions-semantic-injected.json",
                )
                process, payload = self._run(
                    "plan",
                    root2,
                    "--audit",
                    str(audit2),
                    "--template",
                    str(template_path2),
                    "--decisions",
                    str(injected),
                )
                self.assertNotEqual(0, process.returncode)
                self.assertTrue(injected_source.exists())
            finally:
                shutil.rmtree(root2)

    def test_semantic_rehome_rejects_non_minimal_leaf_containers(self):
        """Dirty containers may only use pending isolation, never partial rehome."""

        for kind in ("unknown_file", "child_dir", "multi_video"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                first, container = self._make_dirty_semantic_rehome_fixture(root, kind)
                audit_path, report = self._fresh_audit(root)
                self.assertEqual("FAIL", report["core_gate"]["status"])
                template, template_path = self._template(root, audit_path, "core_exception")
                decisions_path = self._decisions(
                    root,
                    template,
                    "rehome_unit",
                    extra={
                        "resolved_director_name": "正确导演 Correct Director",
                        "resolved_chinese_title": "脏片名",
                        "main_video_name": first.name,
                    },
                    name=f"decisions-semantic-dirty-{kind}.json",
                )
                process, payload = self._run(
                    "plan",
                    root,
                    "--audit",
                    str(audit_path),
                    "--template",
                    str(template_path),
                    "--decisions",
                    str(decisions_path),
                )
                self.assertNotEqual(0, process.returncode, payload)
                self.assertEqual("FAIL", payload.get("status"), payload)
                self.assertTrue(first.exists(), payload)
                self.assertTrue(container.exists(), payload)
                self.assertFalse((root / "正确导演 Correct Director").exists(), payload)

    def test_pending_isolation_moves_dirty_non_anchor_containers_as_whole(self):
        """Pending isolation must preserve every entry in an ordinary dirty container."""

        for kind in ("unknown_file", "child_dir", "multi_video"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _first, container = self._make_dirty_semantic_rehome_fixture(root, kind)
                original_files = {
                    str(path.relative_to(container))
                    for path in container.rglob("*")
                    if path.is_file()
                }
                audit_path, report = self._fresh_audit(root)
                self.assertEqual("FAIL", report["core_gate"]["status"])
                template, template_path = self._template(root, audit_path, "core_exception")
                decisions_path = self._decisions(
                    root,
                    template,
                    "pending_isolation",
                    name=f"decisions-pending-dirty-{kind}.json",
                )
                _plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)
                pending_target = (
                    root
                    / "_待确认_"
                    / f"{template['items'][0]['candidate_id']}-{container.name}"
                )

                process, payload = self._run("apply", root, "--plan", str(plan_path), "--dry-run")
                self.assertEqual(0, process.returncode, payload)
                self.assertTrue(container.exists(), payload)
                self.assertFalse(pending_target.exists(), payload)

                process, payload = self._run("apply", root, "--plan", str(plan_path))
                self.assertEqual(0, process.returncode, payload)
                self.assertFalse(container.exists(), payload)
                self.assertTrue(pending_target.is_dir(), payload)
                self.assertEqual(
                    original_files,
                    {
                        str(path.relative_to(pending_target))
                        for path in pending_target.rglob("*")
                        if path.is_file()
                    },
                    payload,
                )

                process, payload = self._run("verify", root, "--plan", str(plan_path))
                self.assertEqual(0, process.returncode, payload)
                self.assertEqual("PASS", payload["status"], payload)

    def test_pending_batches_reuse_existing_pending_directory(self):
        """Sequential batches must share an existing real _待确认_ directory."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending_targets: list[Path] = []
            for kind in ("unknown_file", "child_dir"):
                _first, container = self._make_dirty_semantic_rehome_fixture(root, kind)
                audit_path, report = self._fresh_audit(root)
                self.assertEqual("FAIL", report["core_gate"]["status"])
                template, template_path = self._template(root, audit_path, "core_exception")
                decisions_path = self._decisions(
                    root,
                    template,
                    "pending_isolation",
                    name=f"decisions-pending-sequential-{kind}.json",
                )
                _plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)
                target = (
                    root
                    / "_待确认_"
                    / f"{template['items'][0]['candidate_id']}-{container.name}"
                )
                pending_targets.append(target)

                process, payload = self._run("apply", root, "--plan", str(plan_path), "--dry-run")
                self.assertEqual(0, process.returncode, payload)
                process, payload = self._run("apply", root, "--plan", str(plan_path))
                self.assertEqual(0, process.returncode, payload)
                self.assertFalse(container.exists(), payload)
                self.assertTrue(target.is_dir(), payload)
                process, payload = self._run("verify", root, "--plan", str(plan_path))
                self.assertEqual(0, process.returncode, payload)
                self.assertEqual("PASS", payload["status"], payload)

            self.assertTrue((root / "_待确认_").is_dir())
            self.assertEqual(2, len([path for path in (root / "_待确认_").iterdir() if path.is_dir()]))
            self.assertTrue(all(path.is_dir() for path in pending_targets))

    def test_mkdir_actions_rejects_file_symlink_and_outside_ancestors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocked_file = root / "blocked-file"
            blocked_file.write_bytes(b"not a directory")
            with self.assertRaises(SLOWPATH_MODULE.SlowpathError):
                SLOWPATH_MODULE._mkdir_actions(root, blocked_file / "child", "test", [])

            blocked_link = root / "blocked-link"
            blocked_link.symlink_to(root / "link-target", target_is_directory=True)
            with self.assertRaises(SLOWPATH_MODULE.SlowpathError):
                SLOWPATH_MODULE._mkdir_actions(root, blocked_link / "child", "test", [])

            with self.assertRaises(SLOWPATH_MODULE.SlowpathError):
                SLOWPATH_MODULE._mkdir_actions(root, root.parent / "outside", "test", [])

    def test_pending_isolation_does_not_move_director_anchor_as_a_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            director = root / "导演 Director"
            selected = self._make(
                root,
                "导演 Director/Orphan.Movie.2020.1080p.WEB-DL.x264-RLS.mkv",
            )
            sibling = self._make(
                root,
                "导演 Director/Another.Movie.2019.720p.WEB-DL.x264-RLS.mkv",
            )
            audit_path, _report = self._fresh_audit(root)
            template, template_path = self._template(root, audit_path, "core_exception")
            decisions_path = self._decisions(
                root,
                template,
                "pending_isolation",
                extra={"main_video_name": selected.name},
                name="decisions-pending-director-anchor.json",
            )
            _plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)
            process, payload = self._run("apply", root, "--dry-run", "--plan", str(plan_path))
            self.assertEqual(0, process.returncode, payload)
            process, payload = self._run("apply", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode, payload)
            self.assertTrue(director.is_dir(), payload)
            self.assertFalse(selected.exists(), payload)
            self.assertTrue(sibling.exists(), payload)
            self.assertTrue(any(path.name == selected.name for path in (root / "_待确认_").rglob("*")))
            self.assertFalse(any(path.name == director.name for path in (root / "_待确认_").rglob("*")))
            process, payload = self._run("verify", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode, payload)
            self.assertEqual("PASS", payload["status"], payload)

    def test_pending_does_not_move_director_root_without_explicit_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = self._make(root, "导演 Director/Orphan.Movie.2020.1080p.WEB-DL.x264-RLS.mkv")
            audit_path, _report = self._fresh_audit(root)
            template, template_path = self._template(root, audit_path, "core_exception")
            decisions_path = self._decisions(root, template, "pending_isolation")
            process, payload = self._run(
                "plan",
                root,
                "--audit",
                str(audit_path),
                "--template",
                str(template_path),
                "--decisions",
                str(decisions_path),
            )
            self.assertNotEqual(0, process.returncode)
            self.assertTrue(source_video.exists())
            self.assertTrue((root / "导演 Director").is_dir())

    def test_root_orphan_pending_moves_only_selected_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = self._make_root_orphan_fixture(root)
            audit_path, _report = self._fresh_audit(root)
            template, template_path = self._template(root, audit_path, "core_exception")
            decisions_path = self._decisions(
                root,
                template,
                "pending_isolation",
                extra={"main_video_name": source_video.name},
                name="decisions-root-pending.json",
            )
            _plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)
            process, payload = self._run("apply", root, "--plan", str(plan_path), "--dry-run")
            self.assertEqual(0, process.returncode)
            process, payload = self._run("apply", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            self.assertTrue(root.is_dir())
            self.assertFalse(source_video.exists())
            self.assertTrue(any((root / "_待确认_").rglob(source_video.name)))
            process, payload = self._run("verify", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)

    def test_root_orphan_rehome_uses_semantic_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = self._make_root_orphan_fixture(root)
            audit_path, _report = self._fresh_audit(root)
            template, template_path = self._template(root, audit_path, "core_exception")
            decisions_path = self._decisions(
                root,
                template,
                "rehome_unit",
                extra={
                    "resolved_director_name": "根导演 Root Director",
                    "resolved_chinese_title": "根片",
                    "main_video_name": source_video.name,
                },
                name="decisions-root-rehome.json",
            )
            _plan, plan_path = self._plan(root, audit_path, template_path, decisions_path)
            process, payload = self._run("apply", root, "--dry-run", "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            process, payload = self._run("apply", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)
            self.assertTrue(root.is_dir())
            self.assertFalse(source_video.exists())
            self.assertEqual(1, len(list((root / "根导演 Root Director").rglob("*.mkv"))))
            process, payload = self._run("verify", root, "--plan", str(plan_path))
            self.assertEqual(0, process.returncode)


if __name__ == "__main__":
    unittest.main()
