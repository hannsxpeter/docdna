import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WIRE_PATH = ROOT / "skill" / "scripts" / "docdna_wire.py"

CODEDNA_BLOCK = """<!-- codedna:start -->
## Code style

Match the conventions in CODEDNA.md.
<!-- codedna:end -->
"""


def load_wire():
    spec = importlib.util.spec_from_file_location("docdna_wire", WIRE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WireTests(unittest.TestCase):
    def setUp(self):
        self.wire = load_wire()

    def test_creates_agents_md_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = self.wire.wire(tmp)
            agents = Path(tmp) / "AGENTS.md"

            self.assertTrue(agents.exists())
            self.assertEqual([item["target"] for item in results], ["agents"])
            self.assertEqual(results[0]["action"], "created")
            self.assertIn("DOCDNA.md", agents.read_text(encoding="utf-8"))

    def test_rerun_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.wire.wire(tmp)
            first = (Path(tmp) / "AGENTS.md").read_text(encoding="utf-8")
            self.wire.wire(tmp)
            second = (Path(tmp) / "AGENTS.md").read_text(encoding="utf-8")

            self.assertEqual(first, second)
            self.assertEqual(second.count(self.wire.START), 1)

    def test_preserves_an_existing_codedna_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents = Path(tmp) / "AGENTS.md"
            agents.write_text("# Repo\n\n" + CODEDNA_BLOCK, encoding="utf-8")
            self.wire.wire(tmp)
            self.wire.wire(tmp)
            text = agents.read_text(encoding="utf-8")

            self.assertEqual(text.count("<!-- codedna:start -->"), 1)
            self.assertEqual(text.count("<!-- codedna:end -->"), 1)
            self.assertEqual(text.count(self.wire.START), 1)
            self.assertIn("Match the conventions in CODEDNA.md.", text)
            self.assertIn("# Repo", text)

    def test_a_duplicated_start_does_not_span_a_sibling_block(self):
        # Two independent find() calls made the replaced span [first start, first end], which here
        # reaches from the stale start, across codedna's whole block, to docdna's only end marker.
        # Replacing that span deleted codedna's content outright.
        text = ("# Repo\n\n<!-- docdna:start -->\nSTALE\n"
                + CODEDNA_BLOCK
                + "<!-- docdna:start -->\nCURRENT\n<!-- docdna:end -->\n")
        out = self.wire.replace_block(text, self.wire.PLAIN_BLOCK, self.wire.START, self.wire.END)

        self.assertIn("Match the conventions in CODEDNA.md.", out)
        self.assertEqual(out.count("<!-- codedna:start -->"), 1)
        self.assertEqual(out.count("<!-- codedna:end -->"), 1)
        self.assertIn("DOCDNA.md", out)
        self.assertNotIn("CURRENT", out)

    def test_a_block_that_encloses_a_sibling_block_is_left_alone(self):
        text = ("# Repo\n\n<!-- docdna:start -->\nOLD\n"
                + CODEDNA_BLOCK
                + "<!-- docdna:end -->\n")
        out = self.wire.replace_block(text, self.wire.PLAIN_BLOCK, self.wire.START, self.wire.END)

        self.assertEqual(out, text)
        self.assertIn("Match the conventions in CODEDNA.md.", out)

    def test_an_enclosing_block_is_reported_as_skipped_and_the_file_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents = Path(tmp) / "AGENTS.md"
            body = ("# Repo\n\n<!-- docdna:start -->\nOLD\n"
                    + CODEDNA_BLOCK
                    + "<!-- docdna:end -->\n")
            agents.write_text(body, encoding="utf-8")
            results = self.wire.wire(tmp)

            self.assertEqual(results[0]["action"], "skipped")
            self.assertEqual(agents.read_text(encoding="utf-8"), body)

    def test_locate_block_classifies_each_layout(self):
        healthy = "a\n" + self.wire.PLAIN_BLOCK
        enclosing = "<!-- docdna:start -->\n" + CODEDNA_BLOCK + "<!-- docdna:end -->\n"

        self.assertEqual(self.wire.locate_block(healthy, self.wire.START, self.wire.END)[2], "found")
        self.assertEqual(self.wire.locate_block(enclosing, self.wire.START, self.wire.END)[2], "conflict")
        self.assertEqual(self.wire.locate_block("nothing here", self.wire.START, self.wire.END)[2], "absent")
        self.assertEqual(self.wire.locate_block("<!-- docdna:start -->\nunterminated\n",
                                                self.wire.START, self.wire.END)[2], "absent")

    def test_an_end_marker_before_a_start_marker_does_not_invert_the_span(self):
        text = "<!-- docdna:end -->\n" + CODEDNA_BLOCK + "<!-- docdna:start -->\nB\n<!-- docdna:end -->\n"
        out = self.wire.replace_block(text, self.wire.PLAIN_BLOCK, self.wire.START, self.wire.END)

        self.assertIn("Match the conventions in CODEDNA.md.", out)
        self.assertEqual(out.count("<!-- codedna:start -->"), 1)

    def test_replace_block_requires_explicit_markers(self):
        text = "# Repo\n\n" + CODEDNA_BLOCK
        updated = self.wire.replace_block(text, self.wire.PLAIN_BLOCK, self.wire.START, self.wire.END)

        self.assertIn("<!-- codedna:start -->", updated)
        self.assertIn(self.wire.START, updated)

    def test_updates_existing_tool_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
            results = self.wire.wire(tmp)
            targets = sorted(item["target"] for item in results)

            self.assertEqual(targets, ["agents", "claude"])
            self.assertFalse((Path(tmp) / "GEMINI.md").exists())

    def test_all_targets_creates_every_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = self.wire.wire(tmp, all_targets=True)
            paths = [Path(item["path"]) for item in results]

            self.assertEqual(len(results), len(self.wire.ALL_TARGETS))
            for path in paths:
                self.assertTrue(path.exists(), "%s was not written" % path)

    def test_cursor_rule_gets_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.wire.wire(tmp, targets=["cursor"])
            rule = Path(tmp) / ".cursor" / "rules" / "docdna.mdc"
            text = rule.read_text(encoding="utf-8")

            self.assertTrue(text.startswith("---\n"))
            self.assertIn("alwaysApply: true", text)
            self.assertIn(self.wire.START, text)

    def test_cascade_prefers_windsurf_only_when_devin_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".windsurf" / "rules").mkdir(parents=True)
            self.assertEqual(self.wire.cascade_path(root).parts[-3:], (".windsurf", "rules", "docdna.md"))

            (root / ".devin" / "rules").mkdir(parents=True)
            self.assertEqual(self.wire.cascade_path(root).parts[-3:], (".devin", "rules", "docdna.md"))

    def test_json_cli_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(WIRE_PATH), "--json", tmp],
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(proc.stdout)

            self.assertEqual(payload[0]["target"], "agents")
            self.assertEqual(payload[0]["action"], "created")


if __name__ == "__main__":
    unittest.main()
