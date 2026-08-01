import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK_PATH = ROOT / "skill" / "scripts" / "docdna_check.py"
SCAN_PATH = ROOT / "skill" / "scripts" / "docdna_scan.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
GIT = shutil.which("git")

SETTINGS = """import os

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
"""

REFORMATTED = """import json
import os

# Every setting is read once, when the module is imported.

DATABASE_URL = os.environ["DATABASE_URL"]

REDIS_URL = os.environ.get(
    "REDIS_URL",
    "redis://localhost:6379/0",
)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
"""

RENAMED = REFORMATTED.replace("LOG_LEVEL", "LOGGING_LEVEL")

BODY = """# Configuration reference

The database URL is read from the process environment when the module is imported
[`src/config/settings.py#DATABASE_URL`].

The Redis URL falls back to a localhost default [`src/config/settings.py#REDIS_URL`].
"""

GAP_PAIR = """
<!-- GAP id=CFG-001 kind=human-input sev=major owner=unassigned doc=build.config-reference
     asks="How long are request logs retained?" -->
> **GAP CFG-001** (major): no retention period is stated in code, config, or CI.
> This is a decision, not a fact, and it must be made by a person.
"""

GAP_COMMENT_ONLY = """
<!-- GAP id=CFG-002 kind=human-input sev=major owner=unassigned doc=build.config-reference
     asks="How long are request logs retained?" -->
"""

GAP_QUOTE_ONLY = """
> **GAP CFG-003** (major): no retention period is stated in code, config, or CI.
> This is a decision, not a fact, and it must be made by a person.
"""

MANIFEST = {
    "schema": 1,
    "tool": "docdna_select",
    "version": "0.1.0",
    "generated_at": "2026-07-31T00:00:00Z",
    "archetype": {"primary": "internal-service", "overlays": []},
    "interview": {},
    "documents": [],
    "excluded": [
        {
            "id": "operate.oncall",
            "title": "On-call and escalation",
            "rule": "rule.operate.oncall",
            "because": "no on-call configuration was committed when this profile was written",
            "revisit_when": {"signal": "ops.oncall", "is": "present"},
        }
    ],
}


def load_check():
    spec = importlib.util.spec_from_file_location("docdna_check", CHECK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frontmatter(pairs):
    lines = ["---"]
    for key, value in pairs:
        if isinstance(value, list):
            lines.append("%s:" % key)
            for item in value:
                lines.append("  - %s" % item)
        else:
            lines.append("%s: %s" % (key, value))
    lines.append("---")
    return "\n".join(lines) + "\n"


def document(covers, extra=None, body=BODY):
    pairs = [("id", "build.config-reference"), ("title", "Configuration reference"),
             ("stage", "build"), ("status", "draft"), ("owner", "unassigned"),
             ("last_reviewed", "2026-07-31"), ("review_cadence", "on-change"),
             ("covers", covers), ("derivation", "derived")]
    pairs.extend(extra or [])
    return frontmatter(pairs) + "\n" + body


def write_repo(root, files):
    for rel in sorted(files):
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[rel], encoding="utf-8")
    return Path(root)


def copy_fixture(name, root):
    target = Path(root) / name
    shutil.copytree(str(FIXTURES / name), str(target))
    return target


def kinds(report, kind):
    return [row for row in report["findings"] if row["kind"] == kind]


def drift_record(report, path):
    for record in report["drift"]["digest"]:
        if record["path"] == path:
            return record
    return None


def cli(repo, *args):
    command = [sys.executable, str(CHECK_PATH), "--no-write"] + list(args) + [str(repo)]
    return subprocess.run(command, text=True, capture_output=True)


def git(root, *args):
    command = ["git", "-C", str(root), "-c", "user.email=tests@example.invalid",
               "-c", "user.name=docdna tests"] + list(args)
    subprocess.run(command, check=True, capture_output=True)


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.check = load_check()

    def check_repo(self, repo, fail_on="major", scan_path=None):
        return self.check.check(str(repo), set(self.check.PASSES), fail_on, scan_path, False)

    def test_covers_naming_a_directory_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                    "docs/build/config-reference.md": document(["src/config"])})
            report = self.check_repo(repo)
            rows = kinds(report, "covers-directory")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "blocker")
            self.assertEqual(rows[0]["pass"], "lint")
            self.assertTrue(rows[0]["gating"])
            self.assertIn("src/config", rows[0]["detail"])
            self.assertIn("saturates the drift test", rows[0]["detail"])

    def test_covers_naming_a_glob_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            covers = ["src/config/*.py"]
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                    "docs/build/config-reference.md": document(covers)})
            report = self.check_repo(repo)
            rows = kinds(report, "covers-glob")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "blocker")
            self.assertTrue(rows[0]["gating"])

    def test_a_reformat_and_an_added_import_do_not_fire_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS})
            digest = self.check.covers_state(str(repo), ["src/config/settings.py"])["digest"]
            extra = [("covers_digest", digest), ("drift_budget", 0)]
            write_repo(tmp, {"docs/build/config-reference.md":
                             document(["src/config/settings.py"], extra)})

            clean = self.check_repo(repo)
            self.assertEqual(kinds(clean, "drift-stale"), [])

            (repo / "src" / "config" / "settings.py").write_text(REFORMATTED, encoding="utf-8")
            after = self.check_repo(repo)
            record = drift_record(after, "docs/build/config-reference.md")

            self.assertEqual(kinds(after, "drift-stale"), [])
            self.assertEqual(record["digest_actual"], digest)
            self.assertEqual(record["changes"], 0)
            self.assertFalse(record["staleness"]["drift_stale"])

    def test_a_renamed_declaration_fires_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS})
            digest = self.check.covers_state(str(repo), ["src/config/settings.py"])["digest"]
            extra = [("covers_digest", digest), ("drift_budget", 0)]
            write_repo(tmp, {"docs/build/config-reference.md":
                             document(["src/config/settings.py"], extra)})
            (repo / "src" / "config" / "settings.py").write_text(RENAMED, encoding="utf-8")

            report = self.check_repo(repo)
            rows = kinds(report, "drift-stale")
            record = drift_record(report, "docs/build/config-reference.md")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "major")
            self.assertNotEqual(record["digest_actual"], digest)
            self.assertTrue(record["staleness"]["drift_stale"])

    def test_drift_budget_defaults_follow_the_stage(self):
        self.assertEqual(self.check.budget_for({"stage": "assure"}),
                         (self.check.TIGHT_BUDGET, "stage default"))
        self.assertEqual(self.check.budget_for({"stage": "design"}),
                         (self.check.TIGHT_BUDGET, "stage default"))
        self.assertEqual(self.check.budget_for({"stage": "build"}),
                         (self.check.LOOSE_BUDGET, "default"))
        self.assertEqual(self.check.budget_for({"stage": "assure", "drift_budget": 7}),
                         (7, "frontmatter"))
        self.assertEqual(self.check.budget_for({"drift_budget": 0}), (0, "frontmatter"))

    @unittest.skipUnless(GIT, "git is not installed")
    def test_drift_budget_is_honoured(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS})
            git(repo, "init", "--quiet")
            git(repo, "add", "src/config/settings.py")
            git(repo, "commit", "--quiet", "-m", "settings")
            commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                    check=True, text=True, capture_output=True).stdout.strip()
            digest = self.check.covers_state(str(repo), ["src/config/settings.py"])["digest"]
            extra = [("covers_digest", digest), ("drift_budget", 2),
                     ("last_validated_commit", commit)]
            write_repo(tmp, {"docs/build/config-reference.md":
                             document(["src/config/settings.py"], extra)})

            settings = repo / "src" / "config" / "settings.py"
            settings.write_text(SETTINGS + 'SENTRY_DSN = os.environ.get("SENTRY_DSN", "")\n'
                                           'STATSD_HOST = os.environ.get("STATSD_HOST", "")\n',
                                encoding="utf-8")
            within = self.check_repo(repo)
            record = drift_record(within, "docs/build/config-reference.md")

            self.assertEqual(record["method"], "git")
            self.assertEqual(record["changes"], 2)
            self.assertEqual(record["budget"], 2)
            self.assertEqual(record["added"], ["SENTRY_DSN", "STATSD_HOST"])
            self.assertEqual(kinds(within, "drift-stale"), [])

            settings.write_text(settings.read_text(encoding="utf-8")
                                + 'OTEL_ENDPOINT = os.environ.get("OTEL_ENDPOINT", "")\n',
                                encoding="utf-8")
            over = self.check_repo(repo)
            rows = kinds(over, "drift-stale")

            self.assertEqual(len(rows), 1)
            self.assertIn("3 declaration changes over budget 2", rows[0]["detail"])

    def test_owner_unassigned_never_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            digest_source = {"src/config/settings.py": SETTINGS}
            repo = write_repo(tmp, digest_source)
            digest = self.check.covers_state(str(repo), ["src/config/settings.py"])["digest"]
            body = BODY + GAP_PAIR
            write_repo(tmp, {"docs/build/config-reference.md":
                             document(["src/config/settings.py"],
                                      [("covers_digest", digest)], body)})
            report = self.check_repo(repo)

            self.assertEqual([row for row in report["findings"] if "owner" in row["kind"]], [])
            self.assertEqual(report["gaps"]["unassigned"], 1)
            self.assertEqual(report["gaps"]["owner_note"], self.check.OWNER_NOTE)
            self.assertEqual(report["summary"]["gating"], 0)
            self.assertEqual(report["summary"]["exit"], 0)
            self.assertEqual(report["documents"][0]["owner"], "unassigned")

    def test_empty_covers_is_unverifiable_and_never_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                    "docs/build/config-reference.md": document([])})
            report = self.check_repo(repo)
            rows = kinds(report, "unverifiable")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "info")
            self.assertFalse(rows[0]["gating"])
            self.assertEqual(report["staleness"]["unverifiable"], 1)
            self.assertEqual(report["summary"]["gating"], 0)
            self.assertEqual(report["summary"]["exit"], 0)

    def test_a_gap_comment_without_a_blockquote_is_a_lint_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                    "docs/build/config-reference.md":
                                    document([], body=BODY + GAP_COMMENT_ONLY)})
            report = self.check_repo(repo)
            rows = kinds(report, "gap-form")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "major")
            self.assertTrue(rows[0]["gating"])
            self.assertIn("no reader-visible blockquote half", rows[0]["detail"])

    def test_a_gap_blockquote_without_a_comment_is_a_lint_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                    "docs/build/config-reference.md":
                                    document([], body=BODY + GAP_QUOTE_ONLY)})
            report = self.check_repo(repo)
            rows = kinds(report, "gap-form")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "major")
            self.assertTrue(rows[0]["gating"])
            self.assertIn("no machine-readable comment half", rows[0]["detail"])

    def test_tripwires_print_before_drift_and_lint(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_fixture("internal_service", tmp)
            write_repo(repo, {".docdna/manifest.json": json.dumps(MANIFEST, indent=2)})
            report = self.check_repo(repo)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                self.check.print_text(report)
            text = buffer.getvalue()

            self.assertEqual(len(report["tripwires"]["firing"]), 1)
            self.assertEqual(report["tripwires"]["firing"][0]["id"], "operate.oncall")
            self.assertIn("TRIPWIRES FIRING", text)
            self.assertLess(text.index("TRIPWIRES FIRING"), text.index("\ndrift, warning"))
            self.assertLess(text.index("TRIPWIRES FIRING"), text.index("\ngaps ("))
            self.assertIn(".pagerduty.yml", text)

    def test_exit_code_is_zero_on_a_clean_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_fixture("agent_skill", tmp)
            process = cli(repo)

            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("exit 0", process.stdout)

    def test_exit_code_is_one_on_a_gated_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                    "docs/build/config-reference.md": document(["src/config"])})
            process = cli(repo, "--fail-on", "major")

            self.assertEqual(process.returncode, 1)
            self.assertIn("exit 1", process.stdout)

    def test_fail_on_never_keeps_the_exit_code_at_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                    "docs/build/config-reference.md": document(["src/config"])})
            process = cli(repo, "--fail-on", "never")

            self.assertEqual(process.returncode, 0, process.stderr)

    def test_drift_does_not_gate_without_an_assurance_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_fixture("documented_repo", tmp)
            report = self.check_repo(repo)
            rows = kinds(report, "drift-stale")

            self.assertEqual(report["config"]["assurance_set"], [])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "major")
            self.assertFalse(rows[0]["gating"])
            self.assertEqual(report["summary"]["exit"], 0)
            self.assertEqual(cli(repo).returncode, 0)

    def test_an_assurance_set_makes_drift_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_fixture("documented_repo", tmp)
            config = {"assurance_set": ["design.data-model"]}
            write_repo(repo, {".docdna/config.json": json.dumps(config, indent=2)})
            report = self.check_repo(repo)
            rows = kinds(report, "drift-stale")

            self.assertEqual(report["config"]["assurance_set"], ["design.data-model"])
            self.assertTrue(rows[0]["gating"])
            self.assertEqual(report["summary"]["gating"], 1)
            self.assertEqual(report["summary"]["exit"], 1)
            self.assertEqual(cli(repo).returncode, 1)

    def test_citation_anchors_are_not_reported_as_path_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_fixture("documented_repo", tmp)
            scan_file = Path(tmp) / "scan.json"
            process = subprocess.run([sys.executable, str(SCAN_PATH), "--json", str(repo)],
                                     check=True, text=True, capture_output=True)
            scan_file.write_text(process.stdout, encoding="utf-8")
            scanned = [row for row in json.loads(process.stdout)["drift"]
                       if row["kind"] == "path-not-found"]
            report = self.check_repo(repo, scan_path=str(scan_file))

            self.assertGreater(len(scanned), 5)
            self.assertTrue(all("#" in row["claim"] for row in scanned))
            self.assertEqual(kinds(report, "scanner-path-not-found"), [])

    def test_internal_service_readme_drift_is_reported_and_does_not_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_fixture("internal_service", tmp)
            report = self.check_repo(repo)
            rows = kinds(report, "scanner-command-not-found")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["path"], "README.md")
            self.assertIn("manage.py runserver", rows[0]["detail"])
            self.assertIn("gunicorn", rows[0]["detail"])
            self.assertFalse(rows[0]["gating"])
            self.assertEqual(report["summary"]["exit"], 0)

    def test_documented_repo_adopts_three_documents_and_lints_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_fixture("documented_repo", tmp)
            report = self.check_repo(repo)
            adopted = sorted(row["id"] for row in report["documents"])

            self.assertEqual(adopted, ["build.config-reference", "build.dev-setup",
                                       "design.data-model"])
            self.assertEqual([row for row in report["findings"] if row["pass"] == "lint"], [])
            self.assertEqual(report["gaps"]["total"], 1)
            self.assertEqual(report["gaps"]["by_kind"], {"human-input": 1})
            self.assertEqual(report["staleness"]["drift_stale"], 1)

    def test_documents_written_under_docs_build_are_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_fixture("documented_repo", tmp)
            report = self.check_repo(repo)
            paths = [row["path"] for row in report["documents"]]

            self.assertIn("docs/build/config-reference.md", paths)
            self.assertIn("docs/build/dev-setup.md", paths)

    @unittest.skipUnless(GIT, "git is not installed")
    def test_documents_under_docs_build_survive_the_git_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_fixture("documented_repo", tmp)
            git(repo, "init", "--quiet")
            git(repo, "add", ".")
            git(repo, "commit", "--quiet", "-m", "documented repo")
            report = self.check_repo(repo)
            paths = [row["path"] for row in report["documents"]]

            self.assertIn("docs/build/config-reference.md", paths)
            self.assertIn("docs/build/dev-setup.md", paths)

    def test_real_build_output_is_still_pruned(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                    "docs/build/config-reference.md": document([]),
                                    "build/generated.md": document([]),
                                    "node_modules/vendored/README.md": "# vendored\n"})
            report = self.check_repo(repo)
            paths = [row["path"] for row in report["documents"]]

            self.assertEqual(paths, ["docs/build/config-reference.md"])

    def test_agent_skill_fixture_raises_the_agent_skill_signal(self):
        process = subprocess.run([sys.executable, str(SCAN_PATH), "--json",
                                  str(FIXTURES / "agent_skill")],
                                 check=True, text=True, capture_output=True)
        signals = {row["id"]: row for row in json.loads(process.stdout)["signals"]}

        self.assertEqual(signals["arch.agent_skill"]["state"], "present")
        self.assertTrue(any(item["path"] == "SKILL.md"
                            for item in signals["arch.agent_skill"]["evidence"]))


if __name__ == "__main__":
    unittest.main()
