import json
import hashlib
from pathlib import Path
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
AGENT_KB_SKILL = ROOT / "skills/agent-kb-workflow/SKILL.md"
ANDROID_SKILL = ROOT / "skills/android-obsidian-self-hosted-git/SKILL.md"
EVALS = ROOT / "skills/agent-kb-workflow/evals/evals.json"
MANIFEST = ROOT / "manifest.json"


class AgentKbCrossDeviceContractTest(unittest.TestCase):
    def test_agent_kb_skill_covers_managed_families_and_seven_instances(self):
        text = AGENT_KB_SKILL.read_text(encoding="utf-8")
        self.assertIn('version: "1.5.0"', text)
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

    def test_evals_include_report_identity_and_graph_boundary_scenarios(self):
        payload = json.loads(EVALS.read_text(encoding="utf-8"))
        prompts = "\n".join(item["prompt"] for item in payload["evals"])
        expected = "\n".join(item["expected_output"] for item in payload["evals"])
        self.assertIn("hermes-vivo-mobile", prompts + expected)
        self.assertIn("codex-ubuntu-desktop", prompts + expected)
        self.assertIn("outputs", prompts + expected)
        self.assertIn("关系图谱", prompts + expected)
        self.assertIn("legacy", prompts + expected)

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
        self.assertEqual("1.5.0", versions["agent-kb-workflow"])
        self.assertEqual("1.1.0", versions["android-obsidian-self-hosted-git"])
        self.assertEqual("1.0.0", versions["maintain-alpha-ficc-terminal"])

    def test_skill_packages_match_complete_source_directories(self):
        for skill_name in (
            "agent-kb-workflow",
            "android-obsidian-self-hosted-git",
            "maintain-alpha-ficc-terminal",
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
