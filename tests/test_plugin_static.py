"""Static package checks: manifests, capability snapshot, and document ingress."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from loader import REPO_ROOT, load_validator

validator = load_validator()


class TestDocumentIngress(unittest.TestCase):
    def test_split_frontmatter_returns_mapping_and_body(self) -> None:
        document = validator.split_frontmatter(
            "---\nname: ds-publisher\n---\nbody line\n", "agents/ds-publisher.md"
        )
        self.assertEqual(document.frontmatter, {"name": "ds-publisher"})
        self.assertEqual(document.body, "body line\n")
        self.assertEqual(document.path, "agents/ds-publisher.md")

    def test_split_frontmatter_rejects_a_file_without_a_block(self) -> None:
        with self.assertRaises(validator.ValidationError) as raised:
            validator.split_frontmatter("no frontmatter here\n", "agents/broken.md")
        self.assertEqual(raised.exception.violation.code, "FrontmatterMissing")

    def test_split_frontmatter_rejects_a_scalar_block(self) -> None:
        with self.assertRaises(validator.ValidationError) as raised:
            validator.split_frontmatter("---\njust a string\n---\nbody\n", "agents/broken.md")
        self.assertEqual(raised.exception.violation.code, "FrontmatterNotMapping")

    def test_split_frontmatter_reports_unparseable_yaml_as_a_violation(self) -> None:
        """A YAML syntax error is an ingress defect like any other, not a traceback."""
        for block in ("name: [unclosed", "a: b\n  c: d", "a: 'unterminated"):
            with self.subTest(block=block):
                with self.assertRaises(validator.ValidationError) as raised:
                    validator.split_frontmatter(f"---\n{block}\n---\nbody\n", "agents/broken.md")
                violation = raised.exception.violation
                self.assertEqual(violation.code, "FrontmatterUnparseable")
                self.assertEqual(violation.path, "agents/broken.md")
                self.assertNotIn("\n", violation.render())

    def test_read_document_reports_bytes_that_are_not_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "broken.md").write_bytes(b"---\nname: x\n---\n\xff\xfe body\n")
            with self.assertRaises(validator.ValidationError) as raised:
                validator.read_document(root / "broken.md", root)
            self.assertEqual(raised.exception.violation.code, "FileNotUtf8")
            self.assertEqual(raised.exception.violation.path, "broken.md")

    def test_read_json_reports_bytes_that_are_not_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "broken.json").write_bytes(b'{"name": "\xff"}')
            with self.assertRaises(validator.ValidationError) as raised:
                validator.read_json(root / "broken.json", root)
            self.assertEqual(raised.exception.violation.code, "FileNotUtf8")


class TestCapabilitySnapshot(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = json.loads((REPO_ROOT / "tests" / "mcp-capabilities.json").read_text(encoding="utf-8"))

    def test_snapshot_carries_fifty_seven_unique_tools(self) -> None:
        tools = validator.load_capabilities(self.snapshot, "tests/mcp-capabilities.json")
        self.assertEqual(len(tools), 57)
        self.assertEqual(len(set(tools)), 57)
        self.assertIn("queue_post", tools)
        self.assertIn("Share-Link", tools)

    def test_load_capabilities_rejects_a_missing_tool_list(self) -> None:
        with self.assertRaises(validator.ValidationError) as raised:
            validator.load_capabilities({"capabilities": {}}, "live")
        self.assertEqual(raised.exception.violation.code, "CapabilityToolsInvalid")


class TestPackageConfig(unittest.TestCase):
    def test_mcp_config_rejects_a_second_server(self) -> None:
        config = {
            "mcpServers": {
                "doublespeed": {"type": "http", "url": validator.MCP_ENDPOINT},
                "other": {"type": "http", "url": "https://example.test/mcp"},
            }
        }
        codes = [violation.code for violation in validator.check_mcp_config(config, ".mcp.json")]
        self.assertEqual(codes, ["McpServerSetInvalid"])

    def test_plugin_manifest_pins_the_catalog_name(self) -> None:
        manifest = validator.read_json(REPO_ROOT / ".grok-plugin" / "plugin.json", REPO_ROOT)
        self.assertEqual(validator.check_plugin_manifest(manifest, ".grok-plugin/plugin.json"), [])
        self.assertEqual(manifest["name"], "doublespeed")

    def test_the_manifest_version_is_validated_as_semver_not_pinned_to_one_release(self) -> None:
        """The catalog version moves on every release. The validator checks its shape, not its value."""
        base = {"name": "doublespeed", "license": "MIT", "description": "x"}
        for version in ("0.1.0", "1.0.0", "12.3.45"):
            with self.subTest(version=version):
                self.assertEqual(validator.check_plugin_manifest({**base, "version": version}, "p.json"), [])
        for version in ("", "  ", "0.1", "1.0.0.0", "v1.0.0", "1.0.0-beta", 1, None):
            with self.subTest(version=version):
                codes = [violation.code for violation in validator.check_plugin_manifest({**base, "version": version}, "p.json")]
                self.assertEqual(codes, ["ManifestVersionInvalid"])

    def test_plugin_manifest_rejects_path_override_arrays(self) -> None:
        manifest = {
            "name": "doublespeed",
            "version": "0.1.0",
            "license": "MIT",
            "description": "x",
            "agents": ["agents/ds-publisher.md"],
        }
        codes = [violation.code for violation in validator.check_plugin_manifest(manifest, ".grok-plugin/plugin.json")]
        self.assertEqual(codes, ["ManifestPathOverride"])


class TestToolClasses(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = validator.read_document(
            REPO_ROOT / "skills" / "doublespeed-content-team" / "references" / "approval-gate.md", REPO_ROOT
        )
        self.classes = validator.parse_tool_class_table(self.gate.body, self.gate.path)
        snapshot = json.loads((REPO_ROOT / "tests" / "mcp-capabilities.json").read_text(encoding="utf-8"))
        self.live_tools = validator.load_capabilities(snapshot, "tests/mcp-capabilities.json")

    def test_every_live_tool_is_classified_exactly_once(self) -> None:
        self.assertEqual(validator.check_class_totality(self.classes, self.live_tools, self.gate.path), [])
        self.assertEqual(len(self.classes), 57)

    def test_class_membership_matches_the_spec_counts(self) -> None:
        counts = {name: 0 for name in validator.TOOL_CLASSES}
        for tool_class in self.classes.values():
            counts[tool_class] += 1
        self.assertEqual(
            counts,
            {
                "READ": 21,
                "SESSION_SCOPE": 1,
                "GENERATE": 18,
                "DRAFT": 5,
                "REVIEW_LINK": 2,
                "REVIEW_STATE": 1,
                "PUBLISH": 5,
                "SETTINGS": 4,
            },
        )

    def test_publish_class_holds_the_five_publishing_tools(self) -> None:
        publish = sorted(tool for tool, name in self.classes.items() if name == "PUBLISH")
        self.assertEqual(publish, ["create_post", "create_posts_bulk", "queue_comments", "queue_post", "update_post"])

    def test_an_unclassified_live_tool_fails(self) -> None:
        violations = validator.check_class_totality(self.classes, tuple(self.live_tools) + ("brand_new_tool",), self.gate.path)
        self.assertEqual([(violation.code, violation.detail) for violation in violations], [("ToolUnclassified", "brand_new_tool")])

    def test_a_classified_tool_missing_from_live_fails(self) -> None:
        classes = dict(self.classes)
        classes["renamed_tool"] = "READ"
        violations = validator.check_class_totality(classes, self.live_tools, self.gate.path)
        self.assertEqual([(violation.code, violation.detail) for violation in violations], [("ToolNotLive", "renamed_tool")])

    def test_duplicate_classification_is_rejected_at_parse_time(self) -> None:
        body = "| `READ` | `get_draft` | allowed |\n| `DRAFT` | `get_draft` | allowed |\n"
        with self.assertRaises(validator.ValidationError) as raised:
            validator.parse_tool_class_table(body, "fake.md")
        self.assertEqual(raised.exception.violation.code, "ToolClassDuplicate")


class TestAgents(unittest.TestCase):
    def setUp(self) -> None:
        gate = validator.read_document(
            REPO_ROOT / "skills" / "doublespeed-content-team" / "references" / "approval-gate.md", REPO_ROOT
        )
        self.classes = validator.parse_tool_class_table(gate.body, gate.path)
        self.agents = [
            validator.parse_agent(validator.read_document(path, REPO_ROOT))
            for path in sorted((REPO_ROOT / "agents").glob("*.md"))
        ]

    def test_the_roster_is_exactly_the_eight_roles(self) -> None:
        self.assertEqual(sorted(agent.name for agent in self.agents), sorted(validator.AGENT_ROSTER))
        self.assertEqual(validator.check_agent_roster(self.agents), [])

    def test_agent_name_matches_the_filename_stem(self) -> None:
        for agent in self.agents:
            self.assertEqual(agent.name, agent.path.rsplit("/", 1)[1][: -len(".md")])

    def test_permissions_are_consistent_with_the_tool_classes(self) -> None:
        self.assertEqual(validator.check_agent_permissions(self.agents, self.classes), [])

    def test_publisher_allowlist_is_exactly_get_draft_and_queue_post(self) -> None:
        publisher = next(agent for agent in self.agents if agent.name == "ds-publisher")
        self.assertEqual(set(publisher.tools), {"get_draft", "queue_post"})

    def test_only_the_director_holds_set_product_and_review_link_tools(self) -> None:
        for agent in self.agents:
            for tool in ("set_product", "create_review_link", "Share-Link"):
                if tool in agent.tools:
                    self.assertEqual(agent.name, "ds-content-director")

    def test_no_agent_holds_a_settings_or_review_state_tool(self) -> None:
        for agent in self.agents:
            for tool in agent.tools:
                self.assertNotIn(self.classes[tool], ("SETTINGS", "REVIEW_STATE"))

    def test_body_allowlist_cannot_drift_from_frontmatter(self) -> None:
        drifted = validator.AgentDefinition(
            path="agents/ds-publisher.md",
            name="ds-publisher",
            description="d",
            tools=("get_draft", "queue_post"),
            body_tools=("get_draft",),
        )
        codes = [violation.code for violation in validator.check_agent_permissions([drifted], self.classes)]
        self.assertIn("AgentAllowlistDrift", codes)

    def test_a_publish_tool_on_another_role_is_rejected(self) -> None:
        rogue = validator.AgentDefinition(
            path="agents/ds-qa-editor.md",
            name="ds-qa-editor",
            description="d",
            tools=("get_draft", "queue_post"),
            body_tools=("get_draft", "queue_post"),
        )
        codes = [violation.code for violation in validator.check_agent_permissions([rogue], self.classes)]
        self.assertIn("AgentClassNotGranted", codes)

    def test_missing_allowed_block_is_a_parse_error(self) -> None:
        document = validator.split_frontmatter(
            "---\nname: ds-publisher\ndescription: d\ntools: [get_draft]\n---\nno block here\n",
            "agents/ds-publisher.md",
        )
        with self.assertRaises(validator.ValidationError) as raised:
            validator.parse_agent(document)
        self.assertEqual(raised.exception.violation.code, "AgentAllowedBlockMissing")


class TestSkills(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_paths = sorted((REPO_ROOT / "skills").glob("*/SKILL.md"))
        self.skills = [validator.parse_skill(validator.read_document(path, REPO_ROOT)) for path in self.skill_paths]

    def test_stage_b_skill_manifest_parses(self) -> None:
        team = next(skill for skill in self.skills if skill.name == "doublespeed-content-team")
        self.assertTrue(team.description.strip())
        self.assertIn("approval", team.description.lower() + team.body.lower())

    def test_duplicate_names_are_reported(self) -> None:
        clash = validator.SkillDefinition(path="skills/x/SKILL.md", name="ds-publisher", description="d", body="")
        agents = [
            validator.AgentDefinition(
                path="agents/ds-publisher.md", name="ds-publisher", description="d",
                tools=("get_draft", "queue_post"), body_tools=("get_draft", "queue_post"),
            )
        ]
        codes = [violation.code for violation in validator.check_skill_names_unique([clash], agents)]
        self.assertEqual(codes, ["NameCollision"])

    def test_a_broken_reference_link_is_reported(self) -> None:
        document = validator.Document(
            path="skills/doublespeed-content-team/SKILL.md",
            frontmatter={"name": "x", "description": "y"},
            body="see [gone](references/gone.md)\n",
        )
        codes = [violation.code for violation in validator.check_reference_links(document, REPO_ROOT)]
        self.assertEqual(codes, ["ReferenceLinkBroken"])

    def test_stage_b_declares_every_step_failure_kind(self) -> None:
        artifacts = validator.read_document(
            REPO_ROOT / "skills" / "doublespeed-content-team" / "references" / "artifacts.md", REPO_ROOT
        )
        self.assertEqual(validator.check_step_failure_kinds(artifacts.body, artifacts.path), [])


class TestStageAIsMcpFree(unittest.TestCase):
    def setUp(self) -> None:
        snapshot = json.loads((REPO_ROOT / "tests" / "mcp-capabilities.json").read_text(encoding="utf-8"))
        self.live_tools = validator.load_capabilities(snapshot, "tests/mcp-capabilities.json")
    def test_the_scan_catches_a_tool_name_in_prose(self) -> None:
        poisoned = validator.Document(
            path="skills/doublespeed-content-audit/SKILL.md", frontmatter={}, body="Then call queue" + "_post to publish."
        )
        violations = validator.check_stage_a_mcp_free([poisoned], self.live_tools)
        self.assertEqual([violation.code for violation in violations], ["StageAReferencesMcpTool"])

    def test_the_scan_catches_a_tool_name_inside_backticks(self) -> None:
        poisoned = validator.Document(
            path="skills/doublespeed-content-audit/SKILL.md", frontmatter={}, body="Use `list" + "_products` first."
        )
        self.assertEqual([violation.code for violation in validator.check_stage_a_mcp_free([poisoned], self.live_tools)], ["StageAReferencesMcpTool"])

    def test_the_scan_catches_a_tool_name_in_a_frontmatter_value(self) -> None:
        """The README claims no live tool name appears anywhere in stage A. Frontmatter is part of
        anywhere: a description is the first thing a host reads out of the skill."""
        poisoned = validator.Document(
            path="skills/doublespeed-content-audit/SKILL.md",
            frontmatter={"name": "doublespeed-content-audit", "description": "Audit a brand, then queue" + "_post the result."},
            body="The prose names no tool.\n",
        )
        self.assertEqual([violation.code for violation in validator.check_stage_a_mcp_free([poisoned], self.live_tools)], ["StageAReferencesMcpTool"])

    def test_the_scan_reads_nested_and_non_string_frontmatter_values(self) -> None:
        poisoned = validator.Document(
            path="skills/doublespeed-content-audit/references/audit-artifacts.md",
            frontmatter={"version": 1, "steps": [{"call": "list" + "_products"}], "enabled": True},
            body="The prose names no tool.\n",
        )
        self.assertEqual([violation.code for violation in validator.check_stage_a_mcp_free([poisoned], self.live_tools)], ["StageAReferencesMcpTool"])

    def test_a_substring_of_a_tool_name_is_not_a_false_positive(self) -> None:
        clean = validator.Document(
            path="skills/doublespeed-content-audit/SKILL.md", frontmatter={}, body="We list products on the website and get a product feel."
        )
        self.assertEqual(validator.check_stage_a_mcp_free([clean], self.live_tools), [])

    def test_stage_a_links_exactly_two_references(self) -> None:
        skill_dir = REPO_ROOT / "skills" / "doublespeed-content-audit"
        self.assertEqual(validator.check_skill_reference_count(skill_dir, 2, REPO_ROOT), [])


class TestSecretScan(unittest.TestCase):
    def test_the_scan_covers_documents_text_and_extensionless_files(self) -> None:
        """A leaked key is a leaked key wherever it lands. Suffix and directory allowlists let a
        secret sit in a design document or a README-adjacent text file unnoticed."""
        for name in ("docs/superpowers/plans/plan.md", "notes.txt", "LICENSE", "Makefile"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("key = " + "a1b2c3d4" * 5 + "\n", encoding="utf-8")
                self.assertEqual([violation.code for violation in validator.check_no_secrets(root)], ["SecretMaterial"])

    def test_the_scan_skips_version_control_and_generated_caches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for rel in (".git/COMMIT_EDITMSG", "scripts/__pycache__/validate.cpython-312.pyc"):
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("key = " + "a1b2c3d4" * 5 + "\n", encoding="utf-8")
            self.assertEqual(validator.check_no_secrets(root), [])

    def test_a_secret_violation_never_repeats_the_matched_value(self) -> None:
        secret = "a1b2c3d4" * 5
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.md").write_text("key = " + secret + "\n", encoding="utf-8")
            violations = validator.check_no_secrets(root)
            self.assertEqual([violation.code for violation in violations], ["SecretMaterial"])
            for violation in violations:
                self.assertNotIn(secret, violation.render())

    def test_the_scan_catches_a_bearer_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.md").write_text("Authorization: " + "Bearer" + " abcdefghijklmnopqrstuvwx\n", encoding="utf-8")
            self.assertEqual([violation.code for violation in validator.check_no_secrets(root)], ["SecretMaterial"])

    def test_the_scan_catches_a_forty_char_hex_string(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.md").write_text("key = " + "a1b2c3d4" * 5 + "\n", encoding="utf-8")
            self.assertEqual([violation.code for violation in validator.check_no_secrets(root)], ["SecretMaterial"])

    def test_the_scan_catches_an_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("X=1\n", encoding="utf-8")
            self.assertEqual([violation.code for violation in validator.check_no_secrets(root)], ["EnvFilePresent"])

    def test_the_pinned_marketplace_sha_is_not_a_secret_false_positive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text('"sha": "' + "0" * 40 + '"\n', encoding="utf-8")
            self.assertEqual(validator.check_no_secrets(root), [])


class TestCollectAndRender(unittest.TestCase):
    def setUp(self) -> None:
        snapshot = json.loads((REPO_ROOT / "tests" / "mcp-capabilities.json").read_text(encoding="utf-8"))
        self.live_tools = validator.load_capabilities(snapshot, "tests/mcp-capabilities.json")

    def test_collect_is_deterministic(self) -> None:
        first = validator.collect_violations(REPO_ROOT, self.live_tools)
        self.assertEqual(first, validator.collect_violations(REPO_ROOT, self.live_tools))

    def test_render_lists_every_violation_once(self) -> None:
        violations = [
            validator.Violation("B", "b.md", "x", "second"),
            validator.Violation("A", "a.md", "y", "first"),
        ]
        rendered = validator.render(violations)
        self.assertEqual(rendered.count("\n"), 1)
        self.assertLess(rendered.index("A"), rendered.index("B"))

    def test_render_of_nothing_is_a_pass_line(self) -> None:
        self.assertEqual(validator.render([]), "validate-plugin: OK, 0 violations")


class TestCli(unittest.TestCase):
    def test_offline_mode_exits_zero(self) -> None:
        self.assertEqual(validator.main(["--offline"]), 0)

    def test_an_unknown_mode_exits_two(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            validator.main(["--nonsense"])
        self.assertEqual(raised.exception.code, 2)

    def test_a_violating_tree_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("X=1\n", encoding="utf-8")
            self.assertEqual(validator.main(["--offline", "--root", str(root)]), 1)

    def test_unparseable_frontmatter_exits_one_without_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tree"
            shutil.copytree(REPO_ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            rubric = root / "skills" / "doublespeed-content-audit" / "references" / "audit-rubric.md"
            rubric.write_text("---\nname: [unclosed\n---\nbody\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(validator.main(["--offline", "--root", str(root)]), 1)
            self.assertIn("FrontmatterUnparseable", captured.getvalue())

    def test_a_file_that_is_not_utf8_exits_one_without_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tree"
            shutil.copytree(REPO_ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            (root / "notes.md").write_bytes(b"plain text then \xff\xfe\n")
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(validator.main(["--offline", "--root", str(root)]), 1)
            self.assertIn("FileNotUtf8", captured.getvalue())

    def test_fetch_capabilities_is_only_reached_in_live_mode(self) -> None:
        with unittest.mock.patch.object(validator, "fetch_capabilities", side_effect=AssertionError("live fetch in offline mode")):
            self.assertEqual(validator.main(["--offline"]), 0)


if __name__ == "__main__":
    unittest.main()
