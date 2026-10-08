"""docdna_check.py and docdna_backfill.py --verify read documents through one claim engine."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skill" / "scripts"
CHECK_PATH = SCRIPTS / "docdna_check.py"
BACKFILL_PATH = SCRIPTS / "docdna_backfill.py"
PROSE_PATH = SCRIPTS / "docdna_prose.py"
FIXTURE = ROOT / "tests" / "fixtures" / "solo_cli"

SETTINGS = """import os

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
"""

BANNER = """> Backfilled by docdna from repository evidence.
> This is derived, not authoritative.
"""

CONTROL = """## Document control

This document was derived from the repository.
"""

CITED = ("The database URL is read from the process environment\n"
         "[`src/config/settings.py#DATABASE_URL`].\n")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_repo(root, files):
    for rel in sorted(files):
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[rel], encoding="utf-8")
    return Path(root)


def render_frontmatter(pairs):
    lines = ["---"]
    for key, value in pairs:
        if isinstance(value, list):
            if not value:
                lines.append("%s: []" % key)
                continue
            lines.append("%s:" % key)
            lines.extend("  - %s" % item for item in value)
        elif value is None:
            lines.append("%s: null" % key)
        else:
            lines.append("%s: %s" % (key, value))
    lines.append("---")
    return "\n".join(lines) + "\n"


def document(body, covers="settings", gap_id="CFG-001"):
    pairs = [("id", "build.config-reference"), ("title", "Configuration reference"),
             ("stage", "build"), ("status", "draft"), ("owner", "unassigned"),
             ("last_reviewed", "2026-07-31"), ("review_cadence", "on-change"),
             ("covers", ["src/config/settings.py"] if covers == "settings" else covers),
             ("derivation", "derived")]
    gap = ("<!-- GAP id=%s kind=human-input sev=major owner=unassigned\n"
           "     doc=build.config-reference asks=\"How long are request logs retained?\" -->\n"
           "> **GAP %s** (major): no retention period is stated in code, config, or CI.\n"
           % (gap_id, gap_id))
    return "%s\n%s\n## Settings\n\n%s\n%s\n%s\n%s" % (render_frontmatter(pairs), BANNER, CITED,
                                                    gap, body, CONTROL)


def kinds(findings, kind):
    return [row for row in findings if row["kind"] == kind]


class SharedEngineTests(unittest.TestCase):
    def setUp(self):
        self.check = load("docdna_check_claims", CHECK_PATH)
        self.backfill = load("docdna_backfill_claims", BACKFILL_PATH)
        self.prose = load("docdna_prose_claims", PROSE_PATH)
        self.claims = sys.modules["docdna_claims"]
        self.catalog = self.backfill.load_documents()

    def both(self, text, files=None):
        with tempfile.TemporaryDirectory() as tmp:
            tree = {"src/config/settings.py": SETTINGS,
                    "docs/build/config-reference.md": text}
            tree.update(files or {})
            repo = write_repo(tmp, tree)
            verified = self.backfill.verify_document(str(repo), "docs/build/config-reference.md",
                                                     self.catalog, {})
            checked = self.check.check(str(repo), set(self.check.PASSES), "major", None, False)
            return verified, checked

    def test_both_tools_hold_one_copy_of_every_shared_rule(self):
        for name in ("claim_blocks", "anchor_spans", "window_around",
                     "inside_repo", "outside_repo", "strip_citations", "unsupported_numbers",
                     "gap_reach", "as_list", "GAP_QUOTE", "BIND_LINES", "PROVENANCE_REGIONS"):
            with self.subTest(name=name):
                self.assertIs(getattr(self.check, name), getattr(self.claims, name))
                self.assertIs(getattr(self.backfill, name), getattr(self.claims, name))
        self.assertIs(self.prose.NUMBER, self.claims.NUMBER_TOKEN)

    def test_a_document_stamped_with_the_planned_digest_is_not_drift_stale(self):
        # backfill hashed rel:name over its own declaration patterns and check hashed rel#name over
        # another extractor, so every backfilled document read as drift-stale on its first check.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            shutil.copytree(str(FIXTURE), str(repo),
                            ignore=shutil.ignore_patterns(".docdna", "DOCDNA.md"))
            process = subprocess.run([sys.executable, str(BACKFILL_PATH), "--only",
                                      "build.dev-setup", "--json", str(repo)],
                                     capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            plan = json.loads(process.stdout)["plans"][0]
            front = plan["frontmatter"]
            self.assertTrue(front["covers"])
            self.assertEqual(front["covers_digest"],
                             self.check.covers_state(str(repo), front["covers"])["digest"])

            body = "\n%s\n# Development setup\n\nSet up the project from its manifest.\n" % (
                plan["banner"])
            write_repo(repo, {plan["output_path"]:
                              render_frontmatter(list(front.items())) + body})
            report = self.check.check(str(repo), {"drift"}, "major", None, False)
            records = [row for row in report["drift"]["digest"]
                       if row["path"] == plan["output_path"]]

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["method"], "digest")
            self.assertEqual(records[0]["changes"], 0)
            self.assertFalse(records[0]["staleness"]["drift_stale"])
            self.assertEqual(kinds(report["findings"], "drift-stale"), [])

    def test_check_and_verify_agree_on_the_gap_window(self):
        # --verify counted a claim block within six lines of a GAP marker as covered, and check
        # reported the same block as uncited.
        near, checked = self.both(document("Retention is a decision nobody has written down.\n"))

        self.assertEqual(near["counts"]["uncited"], 0)
        self.assertGreaterEqual(near["counts"]["gap_covered"], 1)
        self.assertEqual(kinds(checked["findings"], "citation-coverage"), [])

        filler = "\n".join("Filler paragraph number %s stands here.\n" % word
                           for word in ("one", "two", "three", "four"))
        far, checked = self.both(document(filler))

        self.assertGreaterEqual(far["counts"]["uncited"], 1)
        self.assertTrue(kinds(far["findings"], "uncited-claim"))
        self.assertEqual(len(kinds(checked["findings"], "citation-coverage")), 1)

    def test_check_and_verify_agree_that_a_bare_bracketed_span_is_no_citation(self):
        # check counted any bracketed code span as a citation; --verify counted none without an
        # anchor. The cited filler keeps the [`TODO`] block the only candidate, out of GAP reach.
        filler = "\n".join("The Redis URL is read from the environment, note %s "
                           "[`src/config/settings.py#REDIS_URL`].\n" % word
                           for word in ("one", "two", "three"))
        verified, checked = self.both(document(
            filler + "\nThe defaults are documented elsewhere [`TODO`].\n"))
        uncited = kinds(verified["findings"], "uncited-claim")
        rows = kinds(checked["findings"], "citation-coverage")

        self.assertEqual(len(uncited), 1)
        self.assertIn("[`TODO`]", uncited[0]["detail"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["line"], uncited[0]["line"])
        self.assertIn("1 of 5 claim blocks", rows[0]["detail"])

    def test_a_gap_id_carrying_an_underscore_is_read_the_same_by_both_tools(self):
        verified, checked = self.both(document("", gap_id="CFG_001"))

        self.assertEqual([row for row in verified["findings"] if row["kind"] == "gap"], [])
        self.assertEqual(kinds(checked["findings"], "gap-form"), [])

    def test_verify_reads_a_scalar_covers_value_as_one_path(self):
        # A scalar was iterated letter by letter, one "covers names s" blocker per character.
        verified, _ = self.both(document("", covers="src/config/settings.py"))

        self.assertEqual(kinds(verified["findings"], "covers"), [])
        self.assertFalse([row for row in verified["findings"] if row["detail"] == "covers is empty"])

        missing, _ = self.both(document("", covers="src/config/gone.py"))
        rows = kinds(missing["findings"], "covers")
        self.assertEqual(len(rows), 1)
        self.assertIn("src/config/gone.py", rows[0]["detail"])


class BackfillGitBoundTests(unittest.TestCase):
    def setUp(self):
        self.backfill = load("docdna_backfill_git", BACKFILL_PATH)

    def test_git_calls_are_bounded_and_a_timeout_reads_as_no_answer(self):
        expired = subprocess.TimeoutExpired(["git"], self.backfill.GIT_TIMEOUT)
        with tempfile.TemporaryDirectory() as tmp:
            root = self.backfill.safe_bind_root(os.path.abspath(tmp))
            try:
                with mock.patch.object(self.backfill.subprocess, "run",
                                       side_effect=expired) as run:
                    self.assertIsNone(self.backfill.run_git(root, ["commit", "-m", "x"]))
                    self.assertTrue(self.backfill.path_ignored(root, ".docdna/manifest.json"))
            finally:
                root.close()

        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            self.assertEqual(call[1]["timeout"], self.backfill.GIT_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
