import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "skills/agent-kb-workflow/scripts/verify_output_batch.py"


def item(path, text, sections):
    data = text.encode("utf-8")
    return {
        "path": path,
        "expected_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "required_sections": sections,
    }


def write(path, text):
    path.write_text(text, encoding="utf-8")


def run(manifest, root, extra=None):
    cmd = [
        sys.executable,
        str(VERIFIER),
        "--manifest",
        str(manifest),
        "--root",
        str(root),
    ]
    if extra:
        cmd.extend(extra)
    return subprocess.run(cmd, capture_output=True, text=True)


def result(stdout):
    return json.loads(stdout.strip())


class VerifyOutputBatchTest(unittest.TestCase):
    def test_success_exits_zero_and_reports_single_line(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root / "a.md", "# A\n摘要\na\n要点\nb\n实体\nc\n概念\nd\n原文摘录\ne\n")
            write(root / "b.md", "# B\n摘要\nx\n要点\ny\n实体\nz\n概念\nw\n原文摘录\nv\n")
            manifest = {
                "schema_version": "1",
                "files": [
                    item("a.md", "# A\n摘要\na\n要点\nb\n实体\nc\n概念\nd\n原文摘录\ne\n", ["摘要", "要点", "实体", "概念", "原文摘录"]),
                    item("b.md", "# B\n摘要\nx\n要点\ny\n实体\nz\n概念\nw\n原文摘录\nv\n", ["摘要", "要点", "实体", "概念", "原文摘录"]),
                ],
            }
            manifest_path = root / "expected.json"
            write(manifest_path, json.dumps(manifest))
            cp = run(manifest_path, root)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertEqual(len(cp.stdout.splitlines()), 1)
            payload = result(cp.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["expected"], 2)
            self.assertEqual(payload["verified"], 2)
            self.assertEqual(payload["errors"]["manifest_error"], 0)
            self.assertEqual(payload["samples"], [])

    def test_missing_size_hash_and_section_mismatch_exit_one(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root / "b.md", "X" * 50)
            write(root / "c.md", "摘要\n完整内容\n实体\n概念\n原文摘录\n")
            write(root / "d.md", "abcdefghij" * 10)
            manifest = {
                "schema_version": "1",
                "files": [
                    item("a.md", "missing", []),
                    item("b.md", "B" * 100, []),
                    item("c.md", "摘要\n完整内容\n实体\n概念\n原文摘录\n", ["摘要", "要点", "实体", "概念", "原文摘录"]),
                    item("d.md", "0123456789" * 10, []),
                ],
            }
            manifest_path = root / "expected.json"
            write(manifest_path, json.dumps(manifest))
            cp = run(manifest_path, root)
            self.assertEqual(cp.returncode, 1, cp.stderr)
            self.assertEqual(len(cp.stdout.splitlines()), 1)
            payload = result(cp.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["expected"], 4)
            self.assertEqual(payload["verified"], 0)
            self.assertEqual(payload["errors"]["missing"], 1)
            self.assertEqual(payload["errors"]["size_mismatch"], 1)
            self.assertEqual(payload["errors"]["hash_mismatch"], 2)
            self.assertEqual(payload["errors"]["section_mismatch"], 1)
            kinds = {sample["kind"] for sample in payload["samples"]}
            self.assertEqual(kinds, {"missing", "size_mismatch", "hash_mismatch", "section_mismatch"})
            self.assertLessEqual(len(payload["samples"]), 10)

    def test_malicious_paths_and_bad_manifests_exit_two(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = base / "vault"
            root.mkdir()
            outside = base / "outside.md"
            write(outside, "secret")
            try:
                os.symlink(outside, root / "link.md")
                symlink_escape = True
            except OSError:
                symlink_escape = False

            valid_hash = hashlib.sha256(b"x").hexdigest()
            cases = [
                (
                    {"schema_version": "1", "files": [item("../escape.md", "x", [])]},
                    "relative escape",
                ),
                (
                    {"schema_version": "1", "files": [item("/tmp/abs.md", "x", [])]},
                    "absolute path",
                ),
                (
                    {
                        "schema_version": "1",
                        "files": [
                            item("a.md", "x", []),
                            item("a.md", "x", []),
                        ],
                    },
                    "duplicate path",
                ),
                (
                    {
                        "schema_version": "1",
                        "files": [
                            {
                                "path": "a.md",
                                "expected_size": 1,
                                "sha256": "not-a-hash",
                                "required_sections": [],
                            }
                        ],
                    },
                    "invalid hash",
                ),
                (
                    {
                        "schema_version": "1",
                        "files": [
                            {
                                "path": "a.md",
                                "expected_size": 1,
                                "sha256": valid_hash,
                                "required_sections": [],
                                "extra": True,
                            }
                        ],
                    },
                    "unknown field",
                ),
                ({"schema_version": "2", "files": []}, "unsupported schema"),
                ({"files": []}, "missing schema_version"),
                ({"schema_version": "1"}, "missing files"),
            ]
            if symlink_escape:
                cases.append(
                    (
                        {
                            "schema_version": "1",
                            "files": [item("link.md", "x", [])],
                        },
                        "symlink escape",
                    )
                )
            for payload, label in cases:
                with self.subTest(case=label):
                    manifest_path = root / "expected.json"
                    write(manifest_path, json.dumps(payload))
                    cp = run(manifest_path, root)
                    self.assertEqual(cp.returncode, 2, (label, cp.stdout, cp.stderr))
                    self.assertEqual(len(cp.stdout.splitlines()), 1)
                    result_payload = result(cp.stdout)
                    self.assertFalse(result_payload["ok"])
                    self.assertEqual(result_payload["errors"]["manifest_error"], 1)

            bad_json = root / "bad.json"
            write(bad_json, "{not json")
            cp = run(bad_json, root)
            self.assertEqual(cp.returncode, 2)
            self.assertEqual(len(cp.stdout.splitlines()), 1)
            self.assertFalse(result(cp.stdout)["ok"])

    def test_samples_are_bounded_and_parameterizable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            files = []
            for index in range(15):
                name = f"file-{index:02d}.md"
                files.append(item(name, "expected", []))
            manifest = {"schema_version": "1", "files": files}
            manifest_path = root / "expected.json"
            write(manifest_path, json.dumps(manifest))

            cp = run(manifest_path, root)
            self.assertEqual(cp.returncode, 1, cp.stderr)
            self.assertEqual(len(cp.stdout.splitlines()), 1)
            payload = result(cp.stdout)
            self.assertEqual(payload["errors"]["missing"], 15)
            self.assertEqual(len(payload["samples"]), 10)

            cp = run(manifest_path, root, ["--max-samples", "3"])
            self.assertEqual(cp.returncode, 1, cp.stderr)
            self.assertEqual(len(cp.stdout.splitlines()), 1)
            payload = result(cp.stdout)
            self.assertEqual(payload["errors"]["missing"], 15)
            self.assertEqual(len(payload["samples"]), 3)

    def test_usage_errors_exit_two_with_single_line_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest_path = root / "expected.json"
            write(manifest_path, json.dumps({"schema_version": "1", "files": []}))
            cp = run(manifest_path, root, ["--max-samples", "nope"])
            self.assertEqual(cp.returncode, 2)
            self.assertEqual(len(cp.stdout.splitlines()), 1)
            self.assertFalse(result(cp.stdout)["ok"])

            cp = subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER),
                    "--manifest",
                    str(manifest_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(cp.returncode, 2)
            self.assertEqual(len(cp.stdout.splitlines()), 1)
            self.assertFalse(result(cp.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
