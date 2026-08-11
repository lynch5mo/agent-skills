import json
import hashlib
from pathlib import Path
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
AGENT_KB_SKILL = ROOT / "skills/agent-kb-workflow/SKILL.md"
ANDROID_SKILL = ROOT / "skills/android-obsidian-self-hosted-git/SKILL.md"
EVALS = ROOT / "skills/agent-kb-workflow/evals/evals.json"
VERIFIER = ROOT / "skills/agent-kb-workflow/scripts/verify_output_batch.py"
MANIFEST = ROOT / "manifest.json"


class AgentKbCrossDeviceContractTest(unittest.TestCase):
    def test_agent_kb_skill_covers_managed_families_and_seven_instances(self):
        text = AGENT_KB_SKILL.read_text(encoding="utf-8")
        self.assertIn('version: "1.6.0"', text)
        self.assertIn("platforms: [linux, macos, windows, android]", text)
        self.assertRegex(text, r'description:\s*"?Use when')
        for config_key in (
            "agentkb.hermesInstance",
            "agentkb.codexInstance",
            "agentkb.claudeInstance",
        ):
            self.assertIn(config_key, text)
        for instance_id in (
            "hermes-mac",
            "hermes-ubuntu-desktop",
            "hermes-vivo-mobile",
            "codex-mac",
            "codex-ubuntu-desktop",
            "claude-code-mac",
            "claude-code-ubuntu-desktop",
        ):
            self.assertIn(instance_id, text)

    def test_agent_kb_skill_preserves_git_and_obsidian_boundaries(self):
        text = AGENT_KB_SKILL.read_text(encoding="utf-8")
        for required in (
            "ops/agents/legacy-report-baseline.json",
            "ops/scripts/configure_agent_instance.py",
            "ops/scripts/agent_finish.sh",
            "outputs/review/agent_task_summaries/<agent_family>/<instance_id>/",
            "Git-tracked",
            "Obsidian",
            "sync_pending",
            "Rebuild vault cache",
        ):
            self.assertIn(required, text)

    def test_agent_kb_skill_documents_output_safe_large_batch_protocol(self):
        self.assertTrue(VERIFIER.is_file())
        text = AGENT_KB_SKILL.read_text(encoding="utf-8")
        for required in (
            "a command exiting 0 with truncated or partial output is NOT complete proof",
            "one logical document per write",
            "bounded chunking with idempotent retries",
            "retry only failed pieces",
            "wc -l",
            "scripts/verify_output_batch.py",
        ):
            self.assertIn(required, text)
        sop = ROOT / "skills/agent-kb-workflow/references/series-compilation-sop.md"
        sop_text = sop.read_text(encoding="utf-8")
        for required in (
            "Output-Safe Large-Batch Protocol",
            "Byte-capped or structured single-line summaries",
            "Manifest + hash + required-section verification",
            "independently precomputed expected SHA-256",
            "chunk ledger",
            "chunk_id",
            "offset",
            "expected_size",
            "atomic replacement",
            "blind append retries",
            "idempotent",
            "~8K tokens",
            "~50 lines",
            "scripts/verify_output_batch.py",
            "schema_version",
            "expected_size",
            "required_sections",
            "--max-samples",
        ):
            self.assertIn(required, sop_text)
        self.assertNotRegex(sop_text, r"times out when its content payload exceeds")
        self.assertNotRegex(sop_text, r"verify with `wc -l` after each batch")

    def test_evals_include_report_identity_graph_and_output_safety_scenarios(self):
        payload = json.loads(EVALS.read_text(encoding="utf-8"))
        prompts = "\n".join(item["prompt"] for item in payload["evals"])
        expected = "\n".join(item["expected_output"] for item in payload["evals"])
        self.assertIn("hermes-vivo-mobile", prompts + expected)
        self.assertIn("codex-ubuntu-desktop", prompts + expected)
        self.assertIn("outputs", prompts + expected)
        self.assertIn("关系图谱", prompts + expected)
        self.assertIn("legacy", prompts + expected)
        self.assertIn("退出码是 0", prompts)
        self.assertIn("write_file 中途超时", prompts)
        self.assertIn("只重试失败片", expected)
        self.assertIn("SHA-256", expected)
        self.assertIn("独立预计算的 expected size/SHA-256", expected)
        self.assertIn("chunk_id/offset/expected-size/hash", expected)
        self.assertIn("原子替换", expected)

    def test_android_skill_uses_real_vault_discovery_and_instance_binding(self):
        text = ANDROID_SKILL.read_text(encoding="utf-8")
        self.assertIn('version: "1.1.0"', text)
        for required in (
            "/storage/emulated/0/agent-kb",
            "git rev-parse --show-toplevel",
            "git remote get-url origin",
            "core.filemode false",
            "hermes-vivo-mobile",
            "sync_obsidian_graph.sh",
            "Rebuild vault cache",
        ):
            self.assertIn(required, text)

    def test_manifest_versions_match_updated_skills(self):
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        versions = {item["name"]: item["version"] for item in payload["skills"]}
        self.assertEqual("1.6.0", versions["agent-kb-workflow"])
        self.assertEqual("1.1.0", versions["android-obsidian-self-hosted-git"])

    def test_skill_packages_match_complete_source_directories(self):
        for skill_name in (
            "agent-kb-workflow",
            "android-obsidian-self-hosted-git",
        ):
            with self.subTest(skill_name=skill_name):
                source = ROOT / "skills" / skill_name
                expected = {
                    f"{skill_name}/{path.relative_to(source).as_posix()}":
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in source.rglob("*")
                    if path.is_file()
                }
                with zipfile.ZipFile(ROOT / "dist" / f"{skill_name}.skill") as archive:
                    actual = {
                        name: hashlib.sha256(archive.read(name)).hexdigest()
                        for name in archive.namelist()
                        if not name.endswith("/")
                    }
                self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
