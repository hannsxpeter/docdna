import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKFILL_PATH = ROOT / "skill" / "scripts" / "docdna_backfill.py"
CHECK_PATH = ROOT / "skill" / "scripts" / "docdna_check.py"
SCAN_PATH = ROOT / "skill" / "scripts" / "docdna_scan.py"
SELECT_PATH = ROOT / "skill" / "scripts" / "docdna_select.py"
FIXTURES = ROOT / "tests" / "fixtures"

GIT = shutil.which("git")
GIT_STAMP = "2026-07-31T00:00:00 +0000"
DIGIT_HEAD_TRIES = 40

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

CITED_TRUE = ("The database URL is read from the process environment\n"
              "[`src/config/settings.py#DATABASE_URL`].\n")

CITED_FABRICATED = ("The service reads 14 environment variables at import time\n"
                    "[`src/config/settings.py#DATABASE_URL`].\n")

CITED_MISSING_REF = ("The database URL is read from the process environment\n"
                     "[ref: docs/retention-policy.md, verified 2026-07-31].\n")

GAP_ONLY = """<!-- GAP id=CFG-001 kind=human-input sev=major owner=unassigned
     doc=build.config-reference asks="How long are request logs retained?" -->
> **GAP CFG-001** (major): no retention period is stated in code, config, or CI.
"""

FLAT_REQUIREMENTS = "django\nrequests\ngunicorn\n"

DOCKERFILE = "FROM nginx:alpine\nCOPY dist /usr/share/nginx/html\n"

AXIOS_CLIENT = """import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export function fetchCart() {
  return api.get('/cart')
}

export function submitOrder(payload) {
  return api.post('/orders', payload)
}
"""

PROSE_NUMBER = "Request logs are retained for 90 days.\n"

PROBE_RULE = {"id": "rule.probe", "layer": "signal", "because": "a probe rule, never shipped",
              "documents": [], "cite": []}


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


def frontmatter(extra=None):
    pairs = [("id", "build.config-reference"), ("title", "Configuration reference"),
             ("stage", "build"), ("status", "draft"), ("owner", "unassigned"),
             ("last_reviewed", "2026-07-31"), ("review_cadence", "on-change"),
             ("covers", ["src/config/settings.py"]), ("derivation", "derived")]
    for key, value in extra or []:
        pairs = [pair for pair in pairs if pair[0] != key] + [(key, value)]
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


def document(body, extra=None, control=None):
    return "%s\n%s\n## Settings\n\n%s\n%s" % (frontmatter(extra), BANNER, body,
                                              control or CONTROL)


def kinds(findings, kind):
    return [item for item in findings if item["kind"] == kind]


def details(findings, *wanted):
    return [item for item in findings if item["kind"] in wanted]


def states(scan, root):
    report = scan.scan(str(root), set(), False, 5)
    return dict((item["id"], item) for item in report["signals"])


def git(root, *args):
    command = ["git", "-C", str(root), "-c", "user.email=tests@example.invalid",
               "-c", "user.name=docdna tests"] + list(args)
    environment = dict(os.environ, GIT_AUTHOR_DATE=GIT_STAMP, GIT_COMMITTER_DATE=GIT_STAMP)
    return subprocess.run(command, check=True, capture_output=True, text=True,
                          env=environment).stdout.strip()


def head_opening_with_digits(root):
    # A short sha is hex, so five heads in eight open with a digit. Two are wanted, not one: a
    # single leading digit reads as 0 or 1 about as often as not, and docdna does derive a schema
    # number and a version, so a one-digit head can satisfy this test by collision even with the
    # identifier rule switched off. Two digits cannot. The author and committer stamps are pinned,
    # so what git hashes here is the tree and the message alone and the walk lands on the same head
    # on every machine. It returns None rather than looping forever, and the caller skips.
    git(root, "init", "--quiet")
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "-m", "settings")
    for attempt in range(DIGIT_HEAD_TRIES):
        short = git(root, "rev-parse", "--short", "HEAD")
        if short[:2].isdigit():
            return short
        git(root, "commit", "--quiet", "--amend", "-m", "settings %d" % attempt)
    return None


class BackfillVerifyRegressionTests(unittest.TestCase):
    def setUp(self):
        self.backfill = load("docdna_backfill", BACKFILL_PATH)
        self.catalog = self.backfill.load_documents()

    def verify(self, body, extra=None, control=None, files=None):
        with tempfile.TemporaryDirectory() as tmp:
            tree = {"src/config/settings.py": SETTINGS,
                    "docs/build/config-reference.md": document(body, extra, control)}
            tree.update(files or {})
            repo = write_repo(tmp, tree)
            return self.backfill.verify_document(str(repo),
                                                 "docs/build/config-reference.md",
                                                 self.catalog, {})

    def test_a_fabricated_number_in_a_cited_claim_block_fails_verification(self):
        report = self.verify(CITED_FABRICATED)
        rows = kinds(report["findings"], "generated-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "blocker")
        self.assertIn("14", rows[0]["detail"])
        self.assertIn("none of the sources it cites", rows[0]["detail"])

    def test_a_citation_does_not_launder_a_number_the_cited_file_never_states(self):
        # The citation resolves, so the block is cited and the claim reads as sourced. The number
        # is still absent from the file the citation names, which is the whole of the refusal.
        report = self.verify(CITED_FABRICATED)

        self.assertEqual(report["counts"]["cited"], 1)
        self.assertEqual(report["counts"]["uncited"], 0)
        self.assertEqual(kinds(report["findings"], "missing-symbol"), [])
        self.assertTrue(kinds(report["findings"], "generated-number"))

    def test_a_claim_block_whose_numbers_all_sit_in_the_cited_file_passes(self):
        report = self.verify(CITED_TRUE)

        self.assertTrue(report["ok"], report["blockers"])
        self.assertEqual(kinds(report["findings"], "generated-number"), [])

    def test_an_unresolvable_ref_citation_fails_verification(self):
        report = self.verify(CITED_MISSING_REF)
        rows = kinds(report["findings"], "missing-ref")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "blocker")
        self.assertIn("docs/retention-policy.md", rows[0]["detail"])

    def test_a_ref_that_names_no_file_is_refused_rather_than_passed(self):
        report = self.verify("The retention window is stated upstream [ref: , verified "
                             "2026-07-31].\n")

        self.assertFalse(report["ok"])
        self.assertTrue(kinds(report["findings"], "malformed-ref")
                        or kinds(report["findings"], "missing-ref"))

    def test_a_ref_that_lands_in_the_skill_rather_than_the_repository_fails(self):
        # The previous round accepted this at major and left the document verifying clean, on the
        # reasoning that the file exists. It exists in every install of docdna and no author of
        # the repository under analysis controls a word of it, so a ref that lands there laundered
        # the same number into every project that ran the skill.
        report = self.verify("Evidence rules are stated in the skill "
                             "[ref: references/evidence.md, verified 2026-07-31].\n")
        rows = kinds(report["findings"], "ref-outside-repo")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "blocker")
        self.assertIn("references/evidence.md", rows[0]["detail"])
        self.assertIn("not inside this repository", rows[0]["detail"])

    def test_a_ref_that_resolves_inside_the_repository_is_still_accepted(self):
        # The control for the test above. A guard that refused every ref would pass it while
        # making the citation class useless.
        report = self.verify("Retention is stated upstream "
                             "[ref: docs/policy.md#retention, verified 2026-07-31].\n",
                             files={"docs/policy.md": "# Retention\n\nSee the owner.\n"})

        self.assertEqual(kinds(report["findings"], "ref-outside-repo"), [])
        self.assertEqual(kinds(report["findings"], "missing-ref"), [])

    def test_a_fabricated_number_in_the_document_control_table_fails(self):
        # "## Document control" was a one-line trick for parking a figure. The rows of that table
        # are docdna's own provenance, so they answer to what docdna derived and never to nothing.
        control = ("## Document control\n\n"
                   "| | |\n| --- | --- |\n| Retention | 2555 days |\n\n"
                   "This document was derived from the repository.\n")
        report = self.verify(CITED_TRUE, control=control)
        rows = kinds(report["findings"], "provenance-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "blocker")
        self.assertIn("2555", rows[0]["detail"])

    def test_a_fabricated_number_in_a_heading_fails(self):
        report = self.verify(CITED_TRUE + "\n### Availability is 99.99%\n")
        rows = kinds(report["findings"], "generated-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertIn("99.99", rows[0]["detail"])

    def test_a_fabricated_number_in_a_blockquote_fails(self):
        report = self.verify(CITED_TRUE + "\n> The recovery time objective is 4 hours.\n")
        rows = kinds(report["findings"], "generated-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertIn("4", rows[0]["detail"])

    def test_a_fabricated_number_in_a_fenced_block_fails(self):
        report = self.verify(CITED_TRUE + "\n```\nretention_days = 2555\n```\n")
        rows = kinds(report["findings"], "generated-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertIn("2555", rows[0]["detail"])

    def test_a_fabricated_number_in_the_frontmatter_fails(self):
        # Five frontmatter fields carry a policy number and every one is derived from the catalog
        # entry, so --verify recomputes them rather than believing the file.
        report = self.verify(CITED_TRUE, extra=[("retention", "P7Y")])
        rows = kinds(report["findings"], "frontmatter-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "blocker")
        self.assertIn("P7Y", rows[0]["detail"])

    def test_a_fabricated_number_in_a_table_header_row_fails(self):
        # A header row renders to a reader like any other line. It used to be dropped before the
        # number rule ever saw it, which made it one of the two cheapest places in a document to
        # state a commitment nobody had to answer for.
        report = self.verify(CITED_TRUE + "\n| The RTO is 4 hours | Value |\n| --- | --- |\n"
                                          "| a | b |\n")
        rows = kinds(report["findings"], "generated-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertIn("4", rows[0]["detail"])

    def test_a_fabricated_number_in_the_confidence_line_fails(self):
        report = self.verify(CITED_TRUE + "\n_Confidence: medium. The RTO is 4 hours._\n")
        rows = kinds(report["findings"], "generated-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertIn("4", rows[0]["detail"])

    def test_a_number_dressed_as_a_path_in_inline_code_fails(self):
        # A slash alone used to make `99.95/month` look like a repository path and delete it
        # before the number rule ran. A path has a segment with a file extension, or every one of
        # its segments reads as a name.
        report = self.verify(CITED_TRUE + "\nThe availability target is `99.99/100` uptime.\n")
        rows = kinds(report["findings"], "generated-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertIn("99.99", rows[0]["detail"])

    def test_a_gap_marker_does_not_shield_a_fabricated_number_beside_it(self):
        # A GAP marker says a figure is not known. Stating the figure three lines below it is the
        # fabrication the rule exists for, not an exemption from it.
        report = self.verify(CITED_TRUE + "\n" + GAP_ONLY +
                             "\nRequest logs are retained for 2555 days.\n")
        rows = kinds(report["findings"], "generated-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertIn("2555", rows[0]["detail"])

    def test_a_citation_binds_only_the_lines_around_the_place_it_names(self):
        # Proximity binding. The cited file does state 2555, forty lines away from the symbol the
        # citation names, which is a constants module certifying a retention policy by accident.
        far = ("DATABASE_URL = 'x'\n" + "\n".join("# filler %d" % item for item in range(40))
               + "\nRETENTION_DAYS = 2555\n")
        report = self.verify("Request logs are retained for 2555 days "
                             "[`src/config/far.py#DATABASE_URL`].\n",
                             files={"src/config/far.py": far})
        rows = kinds(report["findings"], "generated-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertIn("2555", rows[0]["detail"])
        self.assertIn("within 4 lines", rows[0]["detail"])

    def test_a_citation_binds_the_number_written_at_the_place_it_names(self):
        # The control for the test above, and the false-positive guard on the whole rule.
        near = "RETENTION_DAYS = 2555\nDATABASE_URL = 'x'\n"
        report = self.verify("Request logs are retained for 2555 days "
                             "[`src/config/near.py#RETENTION_DAYS`].\n",
                             files={"src/config/near.py": near})

        self.assertEqual(kinds(report["findings"], "generated-number"), [])

    def test_a_run_citation_is_self_attested_and_the_verdict_is_never_clean(self):
        report = self.verify(CITED_TRUE + "\nThe suite is collected by pytest "
                                          "[run: `pytest --collect-only -q` -> 42 tests].\n")
        rows = kinds(report["findings"], "run-self-attested")

        self.assertEqual(len(rows), 1)
        self.assertIn("SELF-ATTESTED, NOT VERIFIED", rows[0]["detail"])
        self.assertEqual(report["counts"]["run"], 1)
        self.assertEqual(report["counts"]["run_only"], 1)
        self.assertFalse(report["verdict"].startswith("clean"))
        self.assertIn("self-attested", report["verdict"])

    def test_a_document_with_no_run_citation_still_verdicts_clean(self):
        # The control. A verdict that never says clean carries no information.
        report = self.verify(CITED_TRUE)

        self.assertTrue(report["ok"], report["blockers"])
        self.assertEqual(report["verdict"], "clean")

    def test_a_run_citation_never_buys_the_number_written_beside_it(self):
        report = self.verify("Availability measured 99.95% last quarter "
                             "[run: `uptime-report` -> 99.95%].\n")
        rows = kinds(report["findings"], "generated-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertIn("99.95", rows[0]["detail"])

    def test_an_underscore_separated_source_literal_answers_a_plain_claim(self):
        # 1_000_000 in a source file and 1000000 in a claim are one number. This is the
        # false-positive side of the rule and it has to hold, or the rule teaches people to
        # silence it.
        report = self.verify("The ingest rate limit is 1000000 rows a day "
                             "[`src/config/cap.py#MAX_ROWS`].\n",
                             files={"src/config/cap.py": "MAX_ROWS = 1_000_000\n"})

        self.assertEqual(kinds(report["findings"], "generated-number"), [])
        self.assertTrue(report["ok"], report["blockers"])

    def test_a_comma_separated_claim_is_never_answered_by_its_fragments(self):
        # 1,000,000 is one token to answer for, not three that any file in the tree satisfies by
        # accident. The cited file states 1, 000 and 1000 and answers none of it.
        report = self.verify("The rate limit is 1,000,000 requests a day "
                             "[`src/config/frag.py#PAGE`].\n",
                             files={"src/config/frag.py": "PAGE = 1\nCHUNK = 000\nSIZE = 1000\n"})
        rows = kinds(report["findings"], "generated-number")

        self.assertFalse(report["ok"])
        self.assertEqual(len(rows), 1)
        self.assertIn("1000000", rows[0]["detail"])

    def test_verify_refuses_to_certify_a_producible_m_document(self):
        # --verify certifies a document. A producible M instrument is one docdna never writes,
        # because verifying it would mean vouching for decisions that are stated nowhere in the
        # repository, and stamping it verified is worse than never looking at it.
        with tempfile.TemporaryDirectory() as tmp:
            text = document(CITED_TRUE, [("id", "operate.runbook"), ("title", "Runbook")])
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                    "docs/operate/runbook.md": text})
            report = self.backfill.verify_document(str(repo), "docs/operate/runbook.md",
                                                   self.catalog, {})
            rows = kinds(report["findings"], "producible")

            self.assertFalse(report["ok"])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "blocker")
            self.assertIn("operate.runbook is producible M", rows[0]["detail"])

    def test_verify_still_certifies_a_producible_y_document(self):
        # The control. build.config-reference is producible Y and every other test here relies on
        # it verifying at all.
        report = self.verify(CITED_TRUE)

        self.assertEqual(kinds(report["findings"], "producible"), [])
        self.assertTrue(report["ok"], report["blockers"])

    def escaping_citation(self, tmp, target, extra=None):
        # The repository under analysis is a subdirectory, so there is a real file one level above
        # it for the citation to reach. Without a neighbour to reach, a traversal test proves only
        # that a missing file is missing.
        outside = Path(tmp) / "outside"
        outside.mkdir(parents=True, exist_ok=True)
        (outside / "secrets.py").write_text("RETENTION_DAYS = 2555\n", encoding="utf-8")
        body = "Request logs are retained for 2555 days\n[`%s`].\n" % target
        tree = {"src/config/settings.py": SETTINGS,
                "docs/build/config-reference.md": document(body)}
        tree.update(extra or {})
        repo = write_repo(Path(tmp) / "repo", tree)
        return self.backfill.verify_document(str(repo), "docs/build/config-reference.md",
                                             self.catalog, {})

    def test_a_code_citation_that_climbs_out_of_the_repository_is_refused(self):
        # os.path.join happily walks out of the tree, so a citation carrying ../ used to resolve
        # against a file no author of this project controls and bind its numbers into the
        # document. Everything a citation buys has to come from inside the repository being
        # analysed, or a number is sourced to a machine rather than to a repository.
        with tempfile.TemporaryDirectory() as tmp:
            report = self.escaping_citation(tmp, "../outside/secrets.py#RETENTION_DAYS")
            rows = kinds(report["findings"], "path-outside-repo")

            self.assertFalse(report["ok"])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "blocker")
            self.assertIn("../outside/secrets.py", rows[0]["detail"])
            self.assertIn("does not resolve inside the repository", rows[0]["detail"])

    def test_the_number_the_escaping_citation_named_is_refused_with_it(self):
        # The refusal has to reach the number as well as the path. A citation that is rejected and
        # still counted as support would leave 2555 reading as sourced.
        with tempfile.TemporaryDirectory() as tmp:
            report = self.escaping_citation(tmp, "../outside/secrets.py#RETENTION_DAYS")
            rows = kinds(report["findings"], "generated-number")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "blocker")
            self.assertIn("2555", rows[0]["detail"])

    def test_a_citation_that_stays_inside_the_repository_is_still_accepted(self):
        # The control for the two above. A guard that refused every code citation would pass them
        # both and make the citation class useless.
        with tempfile.TemporaryDirectory() as tmp:
            report = self.escaping_citation(
                tmp, "src/config/retention.py#RETENTION_DAYS",
                {"src/config/retention.py": "RETENTION_DAYS = 2555\n"})

            self.assertEqual(kinds(report["findings"], "path-outside-repo"), [])
            self.assertEqual(kinds(report["findings"], "generated-number"), [])


@unittest.skipUnless(GIT, "git is not installed")
class BannerIdentifierRegressionTests(unittest.TestCase):
    # The banner is the one block docdna writes that carries an identifier, and a short sha is hex.
    # When the head happened to open with a digit, the number reader saw a bare figure standing in
    # docdna's own provenance and refused the document docdna had just generated. That is a false
    # accusation against correct output, it lands on five repositories in eight, and a checker that
    # refuses its own output on a coin toss is switched off before it catches anything real.

    def setUp(self):
        self.backfill = load("docdna_backfill", BACKFILL_PATH)
        self.catalog = self.backfill.load_documents()

    def generated_repo(self, tmp, fabricated=None):
        repo = write_repo(tmp, {"src/config/settings.py": SETTINGS})
        short = head_opening_with_digits(repo)
        if short is None:
            self.skipTest("no head opening with digits in %d amendments" % DIGIT_HEAD_TRIES)
        lines = self.backfill.banner_for({"repo_head": short, "dirty": False}).splitlines()
        if fabricated is not None:
            # In place, never appended. banner_lines reads exactly three lines, so a fourth would
            # fall outside the region under test and prove nothing about the banner.
            lines[1] = fabricated
        text = "%s\n%s\n\n## Settings\n\n%s\n%s" % (frontmatter(), "\n".join(lines),
                                                    CITED_TRUE, CONTROL)
        write_repo(repo, {"docs/build/config-reference.md": text})
        return repo, short

    def verify(self, repo):
        return self.backfill.verify_document(str(repo), "docs/build/config-reference.md",
                                             self.catalog, {})

    def test_a_document_generated_at_a_digit_leading_short_sha_verifies_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, short = self.generated_repo(tmp)
            report = self.verify(repo)

            self.assertTrue(short[:1].isdigit(), short)
            self.assertEqual(kinds(report["findings"], "provenance-number"), [])
            self.assertEqual(kinds(report["findings"], "generated-number"), [])
            self.assertTrue(report["ok"], report["blockers"])

    def test_a_fabricated_rto_in_that_same_banner_block_is_still_a_blocker(self):
        # The other half of the same rule, and the half that makes the first half safe. The sha is
        # excused because docdna derived it, not because the banner is excused, so a figure parked
        # beside the sha is read exactly as it would be anywhere else.
        with tempfile.TemporaryDirectory() as tmp:
            repo, short = self.generated_repo(tmp, "> The RTO is 4 hours.")
            report = self.verify(repo)
            rows = kinds(report["findings"], "provenance-number")

            self.assertFalse(report["ok"])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "blocker")
            self.assertIn("4", rows[0]["detail"])
            self.assertIn("banner", rows[0]["detail"])
            self.assertNotIn(short, rows[0]["detail"])


class DeleteGuardRegressionTests(unittest.TestCase):
    def setUp(self):
        self.backfill = load("docdna_backfill", BACKFILL_PATH)
        self.catalog = self.backfill.load_documents()

    def stub_text(self, extra):
        return document(GAP_ONLY, extra)

    def body_hash_of(self, text):
        lines = text.splitlines()
        _, _, body_start = self.backfill.parse_frontmatter(text)
        return self.backfill.body_hash(lines, body_start)

    def run_verify(self, derivation="derived", content_hash=None):
        stamp = date.today().isoformat()
        base = [("derivation", derivation), ("generated_by", "docdna v%s" % self.backfill.VERSION),
                ("generated_on", stamp), ("content_hash", "sha256:%s" % ("0" * 64))]
        settled = self.body_hash_of(self.stub_text(base))
        extra = [pair for pair in base if pair[0] != "content_hash"]
        extra.append(("content_hash", content_hash or settled))
        manifest = {"schema": 1, "documents": [{"id": "build.config-reference",
                                                "title": "Configuration reference",
                                                "write_status": "in-progress",
                                                "plan_generated_at": "%sT00:00:00Z" % stamp}]}
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                ".docdna/manifest.json": json.dumps(manifest, indent=2),
                                "docs/build/config-reference.md": self.stub_text(extra)})
        report = self.backfill.verify_mode(str(repo), "docs/build/config-reference.md",
                                           self.catalog, {}, True, False)
        return report, repo / "docs" / "build" / "config-reference.md"

    def test_a_refused_stub_docdna_wrote_in_this_run_is_removed(self):
        # The control for the two guards below. Without it, a guard that never lets anything
        # through would pass every retention test while doing nothing.
        report, path = self.run_verify()

        self.assertTrue(report["stub_refused"])
        self.assertEqual(report["retained"], [])
        self.assertTrue(report["removed"])
        self.assertFalse(path.exists())

    def test_verify_never_deletes_a_human_authored_document(self):
        report, path = self.run_verify(derivation="human-authored")

        self.assertTrue(report["stub_refused"])
        self.assertFalse(report["removed"])
        self.assertTrue(path.exists())
        self.assertIn("the frontmatter says derivation: human-authored", report["retained"])

    def test_verify_never_deletes_a_document_a_human_edited_after_generation(self):
        report, path = self.run_verify(content_hash="sha256:%s" % ("a" * 64))
        reasons = [item for item in report["retained"] if "content_hash" in item]

        self.assertTrue(report["stub_refused"])
        self.assertFalse(report["removed"])
        self.assertTrue(path.exists())
        self.assertEqual(len(reasons), 1)
        self.assertIn("edited after docdna wrote it", reasons[0])

    def run_verify_with(self, extra_front):
        stamp = date.today().isoformat()
        base = [("derivation", "derived"), ("generated_by", "docdna v%s" % self.backfill.VERSION),
                ("generated_on", stamp), ("content_hash", "sha256:%s" % ("0" * 64))]
        settled = self.body_hash_of(self.stub_text(base))
        extra = [pair for pair in base if pair[0] != "content_hash"]
        extra += list(extra_front)
        extra.append(("content_hash", settled))
        manifest = {"schema": 1, "documents": [{"id": "build.config-reference",
                                                "title": "Configuration reference",
                                                "write_status": "in-progress",
                                                "plan_generated_at": "%sT00:00:00Z" % stamp}]}
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                ".docdna/manifest.json": json.dumps(manifest, indent=2),
                                "docs/build/config-reference.md": self.stub_text(extra)})
        report = self.backfill.verify_mode(str(repo), "docs/build/config-reference.md",
                                           self.catalog, {}, True, False)
        return report, repo / "docs" / "build" / "config-reference.md"

    def test_a_human_who_edits_only_the_frontmatter_of_a_stub_keeps_the_file(self):
        # content_hash is a hash of the body alone, so it cannot see a frontmatter edit at all.
        # Every frontmatter value docdna writes is either derived from the catalog entry or left
        # empty, so both are recomputed and any divergence is a person's hand on the file. The
        # previous round checked the owner and a handful of always-empty keys, so a person who
        # retitled the document, set confidence, or corrected the audience list had edited the
        # file and docdna deleted it anyway.
        for label, extra in (("a retitled document", [("title", "Config reference, reviewed")]),
                             ("a stated confidence", [("confidence", "high")]),
                             ("a corrected audience", [("audiences", "support")]),
                             ("a changed cadence", [("review_cadence", "P90D")])):
            report, path = self.run_verify_with(extra)

            self.assertTrue(report["stub_refused"], label)
            self.assertFalse(report["removed"], label)
            self.assertTrue(path.exists(), label)
            self.assertTrue(report["retained"], label)

    def test_a_human_authored_document_survives_the_cli_with_delete_stub(self):
        stamp = date.today().isoformat()
        extra = [("derivation", "human-authored"),
                 ("generated_by", "docdna v%s" % self.backfill.VERSION),
                 ("generated_on", stamp), ("content_hash", "sha256:%s" % ("0" * 64))]
        text = self.stub_text(extra)
        manifest = {"schema": 1, "documents": [{"id": "build.config-reference",
                                                "title": "Configuration reference",
                                                "write_status": "in-progress",
                                                "plan_generated_at": "%sT00:00:00Z" % stamp}]}
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                    ".docdna/manifest.json": json.dumps(manifest, indent=2),
                                    "docs/build/config-reference.md": text})
            command = [sys.executable, str(BACKFILL_PATH), "--verify",
                       "docs/build/config-reference.md", "--delete-stub", str(repo)]
            process = subprocess.run(command, text=True, capture_output=True)
            path = repo / "docs" / "build" / "config-reference.md"

            self.assertEqual(process.returncode, 1, process.stderr)
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), text)


class CheckNumberRegressionTests(unittest.TestCase):
    def setUp(self):
        self.check = load("docdna_check", CHECK_PATH)

    def prose_repo(self, tmp):
        body = ("# Configuration reference\n\n"
                "The database URL is read from the environment "
                "[`src/config/settings.py#DATABASE_URL`].\n\n" + PROSE_NUMBER)
        return write_repo(tmp, {"src/config/settings.py": SETTINGS,
                                "docs/build/config-reference.md": frontmatter() + "\n" + body})

    def test_check_flags_an_uncited_number_in_human_prose(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.prose_repo(tmp)
            report = self.check.check(str(repo), set(self.check.PASSES), "major", None, False)
            rows = kinds(report["findings"], "generated-number")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "major")
            self.assertEqual(rows[0]["pass"], "lint")
            self.assertIn("90", rows[0]["detail"])
            self.assertIn("retained", rows[0]["detail"])

    def test_check_leaves_the_flagged_file_exactly_as_it_found_it(self):
        # check reports on prose and never edits or removes it. The defect this pins was a check
        # that answered a flagged number by deleting the document that carried it.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.prose_repo(tmp)
            path = repo / "docs" / "build" / "config-reference.md"
            before = path.read_text(encoding="utf-8")
            report = self.check.check(str(repo), set(self.check.PASSES), "major", None, False)

            self.assertTrue(kinds(report["findings"], "generated-number"))
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_the_cli_flags_the_number_and_still_leaves_the_file_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.prose_repo(tmp)
            path = repo / "docs" / "build" / "config-reference.md"
            before = path.read_text(encoding="utf-8")
            command = [sys.executable, str(CHECK_PATH), "--no-write", "--fail-on", "major",
                       "--json", str(repo)]
            process = subprocess.run(command, text=True, capture_output=True)
            report = json.loads(process.stdout)

            self.assertEqual(process.returncode, 1, process.stderr)
            self.assertTrue(kinds(report["findings"], "generated-number"))
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def repo_with(self, tmp, body, control=None, files=None):
        tree = {"src/config/settings.py": SETTINGS,
                "docs/build/config-reference.md": document(body, None, control)}
        tree.update(files or {})
        return write_repo(tmp, tree)

    def findings_for(self, body, control=None, files=None):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo_with(tmp, body, control, files)
            report = self.check.check(str(repo), set(self.check.PASSES), "major", None, False)
            return report["findings"]

    def test_check_binds_a_citation_to_the_lines_around_the_place_it_names(self):
        # check and docdna_backfill.py --verify read the same lines, and until this round they
        # disagreed about what a citation buys: --verify bound a citation to the place it named
        # and check bought every digit anywhere in the file. Two tools that disagree about the
        # same document are worse than either being wrong alone.
        far = ("DATABASE_URL = 'x'\n" + "\n".join("# filler %d" % item for item in range(40))
               + "\nRETENTION_DAYS = 2555\n")
        rows = kinds(self.findings_for("Request logs are retained for 2555 days "
                                       "[`src/config/far.py#DATABASE_URL`].\n",
                                       files={"src/config/far.py": far}), "generated-number")

        self.assertEqual(len(rows), 1)
        self.assertIn("2555", rows[0]["detail"])
        self.assertIn("within 4 lines", rows[0]["detail"])

    def test_check_accepts_the_number_written_at_the_place_the_citation_names(self):
        near = "RETENTION_DAYS = 2555\nDATABASE_URL = 'x'\n"
        rows = kinds(self.findings_for("Request logs are retained for 2555 days "
                                       "[`src/config/near.py#RETENTION_DAYS`].\n",
                                       files={"src/config/near.py": near}), "generated-number")

        self.assertEqual(rows, [])

    def test_check_reads_a_fabricated_number_in_the_document_control_table(self):
        control = ("## Document control\n\n"
                   "| | |\n| --- | --- |\n| Retention | 2555 days |\n\n"
                   "This document was derived from the repository.\n")
        rows = kinds(self.findings_for(CITED_TRUE, control=control), "provenance-number")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "major")
        self.assertIn("2555", rows[0]["detail"])

    def test_check_reports_a_run_citation_as_self_attested_and_never_as_support(self):
        rows = self.findings_for("Availability measured 99.95% last quarter "
                                 "[run: `uptime-report` -> 99.95%].\n")
        attested = kinds(rows, "run-self-attested")
        numbers = kinds(rows, "generated-number")

        self.assertEqual(len(attested), 1)
        self.assertIn("SELF-ATTESTED, NOT VERIFIED", attested[0]["detail"])
        self.assertEqual(len(numbers), 1)
        self.assertIn("99.95", numbers[0]["detail"])

    def test_check_reads_a_number_a_gap_marker_stands_beside(self):
        rows = kinds(self.findings_for(CITED_TRUE + "\n" + GAP_ONLY +
                                       "\nRequest logs are retained for 2555 days.\n"),
                     "generated-number")

        self.assertEqual(len(rows), 1)
        self.assertIn("2555", rows[0]["detail"])

    def test_check_reads_a_table_header_row_and_the_confidence_line(self):
        header = kinds(self.findings_for(CITED_TRUE + "\n| The RTO is 4 hours | Value |\n"
                                                      "| --- | --- |\n| a | b |\n"),
                       "generated-number")
        confidence = kinds(self.findings_for(CITED_TRUE +
                                             "\n_Confidence: medium. The RTO is 4 hours._\n"),
                           "generated-number")

        self.assertEqual(len(header), 1)
        self.assertEqual(len(confidence), 1)

    def test_check_reads_a_number_dressed_as_a_path_in_inline_code(self):
        rows = kinds(self.findings_for(CITED_TRUE +
                                       "\nThe availability target is `99.99/100` uptime.\n"),
                     "generated-number")

        self.assertEqual(len(rows), 1)
        self.assertIn("99.99", rows[0]["detail"])

    def test_check_still_ignores_the_digits_inside_a_real_repository_path(self):
        # The false-positive side of the same rule. A path is verbatim repository evidence and
        # the digits inside it are not a claim about the world.
        rows = kinds(self.findings_for(CITED_TRUE +
                                       "\nThe retention job lives in `src/jobs/v2/purge.py`.\n"),
                     "generated-number")

        self.assertEqual(rows, [])

    def test_an_underscore_separated_source_literal_answers_a_plain_claim_in_check(self):
        rows = kinds(self.findings_for("The ingest rate limit is 1000000 rows a day "
                                       "[`src/config/cap.py#MAX_ROWS`].\n",
                                       files={"src/config/cap.py": "MAX_ROWS = 1_000_000\n"}),
                     "generated-number")

        self.assertEqual(rows, [])

    def test_a_comma_separated_claim_is_never_answered_by_its_fragments_in_check(self):
        rows = kinds(self.findings_for("The rate limit is 1,000,000 requests a day "
                                       "[`src/config/frag.py#PAGE`].\n",
                                       files={"src/config/frag.py":
                                              "PAGE = 1\nCHUNK = 000\nSIZE = 1000\n"}),
                     "generated-number")

        self.assertEqual(len(rows), 1)
        self.assertIn("1000000", rows[0]["detail"])

    def test_a_count_of_files_beside_a_refused_commitment_is_not_flagged(self):
        # The sentence that named the round. Two rounds of tightening left the rule matching a
        # commitment term and a value anywhere in the same block, so this read as an SLA of 3: a
        # count of files on one side of the comma, a refusal to state an SLA on the other, and
        # nothing in between that binds them. Correct prose, accused. A checker that does this is
        # switched off in week two and takes the whole feature with it.
        rows = kinds(self.findings_for(CITED_TRUE + "\nThere are 3 configuration files, and none "
                                                    "of them sets an SLA.\n"),
                     "generated-number")

        self.assertEqual(rows, [])

    def test_a_pointer_to_where_a_policy_is_written_is_not_flagged(self):
        # The same false accusation in its other shape. "described in" reports where a decision is
        # recorded; it does not state the decision. A structural pointer is a place in a document,
        # never a value somebody committed to.
        rows = kinds(self.findings_for(CITED_TRUE + "\nThe retention policy is described in "
                                                    "section 2 of the handbook.\n"),
                     "generated-number")

        self.assertEqual(rows, [])

    def test_an_uncited_retention_period_is_still_flagged(self):
        # The recall side, and the reason the two tests above are not simply the rule switched
        # off. This sentence states a period nothing in the repository backs, and it is exactly
        # what the rule exists to catch.
        rows = kinds(self.findings_for(CITED_TRUE + "\n" + PROSE_NUMBER), "generated-number")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "major")
        self.assertIn("90", rows[0]["detail"])
        self.assertIn("retained", rows[0]["detail"])

    def test_no_docdna_script_ever_removes_a_path(self):
        # The blast radius, stated as a property. docdna_backfill.py owns the one os.remove in the
        # tree, and it sits behind delete_guard.
        for name in ("docdna_check", "docdna_scan", "docdna_select", "docdna_llms", "docdna_wire"):
            source = (ROOT / "skill" / "scripts" / ("%s.py" % name)).read_text(encoding="utf-8")
            for call in ("os.remove(", "os.unlink(", "shutil.rmtree(", "os.rmdir(", "Path.unlink"):
                self.assertNotIn(call, source, "%s calls %s" % (name, call))


class ScanRegressionTests(unittest.TestCase):
    def setUp(self):
        self.scan = load("docdna_scan", SCAN_PATH)

    def test_iface_http_fires_on_a_django_url_conf(self):
        results = states(self.scan, FIXTURES / "internal_service")
        paths = [item["path"] for item in results["iface.http"]["evidence"]]

        self.assertEqual(results["iface.http"]["state"], "present")
        self.assertIn("config/urls.py", paths)

    def test_iface_http_stays_silent_on_the_client_spa(self):
        results = states(self.scan, FIXTURES / "client_spa")

        self.assertNotEqual(results["iface.http"]["state"], "present",
                            results["iface.http"]["evidence"])

    def test_iface_http_stays_silent_on_the_client_spa_once_the_gate_is_satisfied(self):
        # Without the Dockerfile the gate never opens and the bare fixture proves nothing. The
        # axios module is the other half: api.get( and api.post( match the route patterns outright,
        # so only the same-file corroboration keeps the verdict off a browser HTTP client.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "client_spa"
            shutil.copytree(str(FIXTURES / "client_spa"), str(repo))
            write_repo(repo, {"Dockerfile": DOCKERFILE, "src/api/client.js": AXIOS_CLIENT})
            results = states(self.scan, repo)

            self.assertEqual(results["deploy.container"]["state"], "present")
            self.assertEqual(results["iface.http"]["state"], "absent",
                             results["iface.http"]["evidence"])

    def test_iface_http_separates_the_django_router_from_the_vue_router(self):
        # One assertion pair, because the pin is the contrast: both fixtures ship a file that
        # registers routes under a name spelled "router", and only one of them is a server.
        django = states(self.scan, FIXTURES / "internal_service")["iface.http"]
        spa = states(self.scan, FIXTURES / "client_spa")["iface.http"]

        self.assertEqual(django["state"], "present")
        self.assertNotEqual(spa["state"], "present", spa["evidence"])

    def test_supply_has_deps_fires_on_a_flat_requirements_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"requirements.txt": FLAT_REQUIREMENTS,
                                    "app.py": "print('hi')\n"})
            results = states(self.scan, repo)
            evidence = results["supply.has_deps"]["evidence"]

            self.assertEqual(results["supply.has_deps"]["state"], "present")
            self.assertEqual(sorted(set(item["path"] for item in evidence)),
                             ["requirements.txt"])

    def test_supply_has_deps_fires_on_a_pinned_requirements_txt(self):
        results = states(self.scan, FIXTURES / "internal_service")
        paths = [item["path"] for item in results["supply.has_deps"]["evidence"]]

        self.assertEqual(results["supply.has_deps"]["state"], "present")
        self.assertIn("requirements.txt", paths)

    def test_supply_has_deps_stays_absent_when_nothing_declares_a_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, {"app.py": "print('hi')\n"})
            results = states(self.scan, repo)

            self.assertNotEqual(results["supply.has_deps"]["state"], "present")


class ValidatorRegressionTests(unittest.TestCase):
    def setUp(self):
        self.select = load("docdna_select", SELECT_PATH)
        self.catalog = self.select.load_catalog()

    def errors_for(self, effect, when):
        rule = dict(PROBE_RULE, effect=effect, when=when)
        shipped = self.catalog["rules"]
        self.catalog["rules"] = [rule]
        try:
            errors = []
            self.select.check_rules(self.catalog, errors)
        finally:
            self.catalog["rules"] = shipped
        return [item for item in errors if item.startswith("I4")]

    def test_a_require_rule_reaching_a_hint_through_a_not_is_rejected(self):
        errors = self.errors_for("require", {"not": {"signal": "jur.eu", "is": "absent"}})

        self.assertEqual(len(errors), 1)
        self.assertIn("jur.eu", errors[0])
        self.assertIn("effect=require", errors[0])

    def test_a_require_rule_reaching_a_hint_through_a_buried_not_is_rejected(self):
        errors = self.errors_for("require",
                                 {"all": [{"signal": "data.ddl", "is": "present"},
                                          {"any": [{"not": {"signal": "jur.eu",
                                                            "is": "absent"}}]}]})

        self.assertEqual(len(errors), 1)
        self.assertIn("jur.eu", errors[0])

    def test_a_require_rule_naming_the_hint_state_outright_is_rejected(self):
        errors = self.errors_for("require", {"signal": "jur.eu", "is": "hint"})

        self.assertEqual(len(errors), 1)
        self.assertIn("jur.eu", errors[0])

    def test_a_soft_effect_may_still_read_a_hint_through_a_not(self):
        self.assertEqual(self.errors_for("ask", {"not": {"signal": "jur.eu", "is": "absent"}}), [])
        self.assertEqual(self.errors_for("note", {"not": {"signal": "jur.eu", "is": "absent"}}), [])

    def test_a_require_rule_on_a_signal_that_is_not_hint_capped_is_accepted(self):
        self.assertEqual(self.errors_for("require",
                                         {"not": {"signal": "data.pii", "is": "absent"}}), [])

    def test_every_hint_capped_signal_is_probed_not_pattern_matched(self):
        capped = sorted(signal["id"] for signal in self.catalog["signals"]
                        if signal.get("max_state") == self.select.HINT_MAX_STATE)

        self.assertTrue(capped)
        for signal_id in capped:
            errors = self.errors_for("require", {"not": {"signal": signal_id, "is": "absent"}})
            self.assertEqual(len(errors), 1, signal_id)

    def test_the_shipped_catalog_carries_no_hint_dependent_verdict(self):
        errors = []
        self.select.check_rules(self.catalog, errors)

        self.assertEqual([item for item in errors if item.startswith("I4")], [])

    def test_a_hint_in_a_documents_selects_on_is_rejected(self):
        # selects_on sets the baseline verdict directly, so it is a path from a signal to a
        # verdict exactly as much as rules.json when is.
        shipped = self.catalog["documents"]
        probe = dict(shipped[0], selects_on={"not": {"signal": "jur.eu", "is": "absent"}})
        self.catalog["documents"] = [probe]
        try:
            errors = []
            self.select.check_documents(self.catalog, errors)
        finally:
            self.catalog["documents"] = shipped
        rows = [item for item in errors if item.startswith("I4")]

        self.assertEqual(len(rows), 1)
        self.assertIn("jur.eu", rows[0])
        self.assertIn("selects_on", rows[0])

    def test_a_hint_in_an_archetype_weight_is_rejected(self):
        # The archetype score picks the primary, and the primary is the argument to every
        # {"archetype": X} rule in the catalog.
        rows = self.archetype_errors(weights=[{"when": {"not": {"signal": "jur.eu",
                                                                "is": "absent"}},
                                               "points": 3}])

        self.assertEqual(len(rows), 1)
        self.assertIn("jur.eu", rows[0])
        self.assertIn("weights", rows[0])

    def test_a_hint_in_an_overlay_trigger_is_rejected(self):
        # An overlay adds documents through adds and feeds every {"overlay": X} rule.
        rows = self.archetype_errors(overlay_when={"not": {"signal": "jur.eu", "is": "absent"}})

        self.assertEqual(len(rows), 1)
        self.assertIn("jur.eu", rows[0])
        self.assertIn(".when", rows[0])

    def test_a_hint_named_in_requires_absent_is_rejected(self):
        # requires_absent zeroes an archetype when the signal reaches present, and a hint-capped
        # signal never reaches present. Naming one reads as a guard and can never fire.
        rows = self.archetype_errors(requires_absent=["jur.eu"])

        self.assertEqual(len(rows), 1)
        self.assertIn("jur.eu", rows[0])
        self.assertIn("requires_absent", rows[0])

    def test_a_hint_in_an_exclusion_tripwire_is_rejected(self):
        # A firing tripwire tells the reader that a document excluded earlier is now required.
        # That sentence is a verdict wherever it is printed.
        rule = dict(PROBE_RULE, effect="exclude", when={"always": True},
                    because="a probe", cite=["data.ddl"], documents=[],
                    revisit_when={"not": {"signal": "jur.eu", "is": "absent"}})
        shipped = self.catalog["rules"]
        self.catalog["rules"] = [rule]
        try:
            errors = []
            self.select.check_rules(self.catalog, errors)
        finally:
            self.catalog["rules"] = shipped
        rows = [item for item in errors if item.startswith("I4")]

        self.assertEqual(len(rows), 1)
        self.assertIn("jur.eu", rows[0])
        self.assertIn("revisit_when", rows[0])

    def test_a_legitimate_eight_leaf_rule_is_accepted(self):
        # The check partially evaluates the predicate twice rather than enumerating the worlds its
        # terms describe. The version it replaced bailed out over a world cap and reported the
        # bail-out as "this rule turns on a hint", which was not true of the rule and was a worse
        # failure than no check at all. Eight leaves, none of them hint capped, none rejected.
        eight = {"all": [{"signal": "data.ddl", "is": "present"},
                         {"signal": "deploy.cd", "is": "present"},
                         {"signal": "iface.http", "is": "present"},
                         {"signal": "sec.authn", "is": "present"},
                         {"signal": "data.pii", "is": "present"},
                         {"signal": "supply.has_deps", "is": "present"},
                         {"signal": "deploy.container", "is": "present"},
                         {"signal": "sec.compliance_program", "is": "present"}]}

        self.assertEqual(len(self.select.predicate_leaves(eight, [])), 8)
        self.assertEqual(self.errors_for("require", eight), [])

    def archetype_errors(self, weights=None, overlay_when=None, requires_absent=None):
        archetypes = self.catalog["archetypes"]
        primary = dict(archetypes["primaries"][0])
        overlay = dict(archetypes["overlays"][0])
        if weights is not None:
            primary["weights"] = weights
        if requires_absent is not None:
            primary["requires_absent"] = requires_absent
        if overlay_when is not None:
            overlay["when"] = overlay_when
        self.catalog["archetypes"] = {"primaries": [primary], "overlays": [overlay],
                                      "floor": archetypes["floor"],
                                      "counterfactual_margin": archetypes["counterfactual_margin"]}
        try:
            errors = []
            self.select.check_archetypes(self.catalog, errors)
        finally:
            self.catalog["archetypes"] = archetypes
        return [item for item in errors if item.startswith("I4")]


class InterviewRegressionTests(unittest.TestCase):
    FR_CA = {"src/locales/fr-CA/messages.json": "{\"hello\": \"bonjour\"}\n",
             "src/notify.py": "ENDPOINT = \"https://notification.canada.ca/v2/notifications\"\n",
             "pyproject.toml": "[project]\nname = \"thing\"\nversion = \"0.1.0\"\n",
             "README.md": "# thing\n"}

    def setUp(self):
        self.select = load("docdna_select", SELECT_PATH)
        self.scan = load("docdna_scan", SCAN_PATH)

    def surveyed(self, tmp):
        repo = write_repo(tmp, self.FR_CA)
        manifest, _ = self.select.select(str(repo), None, [], False)
        return repo, manifest

    def test_a_jurisdiction_hint_opens_a_question_and_never_resolves_the_answer(self):
        # interview.json default_from is the quietest of the five paths from a signal to a
        # verdict, because an answer is the strongest layer in the lattice. A hint that reaches
        # one leaves the answer at its fallback and reports what it would have written, with its
        # blast radius, as an open question.
        with tempfile.TemporaryDirectory() as tmp:
            repo, manifest = self.surveyed(tmp)
            states = dict((item["id"], item["state"])
                          for item in self.scan.scan(str(repo), set(), False, 5)["signals"])
            row = manifest["interview"]["q3_authorizer"]
            opens = [item for item in manifest["open_questions"]
                     if item["answer"] == "q3_authorizer"]

            self.assertEqual(states["jur.gc"], "hint")
            self.assertEqual(row["value"], "none")
            self.assertEqual(row["source"], "hint-prompted")
            self.assertEqual(row["prompted_by"]["value"], "government-authorizer")
            self.assertEqual(len(opens), 1)
            self.assertEqual(opens[0]["would_be"], "government-authorizer")
            self.assertEqual(opens[0]["assumed"], "none")
            self.assertTrue(opens[0]["becomes_required"] > 0)

    def test_a_user_answer_resolves_what_the_hint_was_not_allowed_to(self):
        # The control. The question the hint opened is answerable, and answering it moves the
        # documents the open question said it would.
        with tempfile.TemporaryDirectory() as tmp:
            repo = write_repo(tmp, self.FR_CA)
            manifest, _ = self.select.select(str(repo), None,
                                             ["q3_authorizer=government-authorizer"], False)
            row = manifest["interview"]["q3_authorizer"]
            opens = [item for item in manifest["open_questions"]
                     if item["answer"] == "q3_authorizer"]

            self.assertEqual(row["value"], "government-authorizer")
            self.assertEqual(row["source"], "user")
            self.assertEqual(opens, [])


class TrapFixtureRegressionTests(unittest.TestCase):
    TRAPS = ("client_spa", "weather_api", "gdpr_lib", "region_const")
    QUIET = ("iface.http", "sec.weak_crypto", "data.pii")

    def setUp(self):
        self.scan = load("docdna_scan", SCAN_PATH)

    def test_no_trap_fixture_fires_a_quiet_signal_or_a_jurisdiction_verdict(self):
        for name in self.TRAPS:
            results = states(self.scan, FIXTURES / name)
            for signal_id in self.QUIET:
                self.assertNotEqual(results[signal_id]["state"], "present",
                                    "%s fired on %s: %s"
                                    % (signal_id, name, results[signal_id]["evidence"]))
            for signal_id, item in sorted(results.items()):
                if signal_id.startswith("jur."):
                    self.assertNotEqual(item["state"], "present",
                                        "%s reached present on %s: %s"
                                        % (signal_id, name, item["evidence"]))


class CheckCitationEscapeRegressionTests(unittest.TestCase):
    # docdna_backfill.py --verify already refused a citation that leaves the repository. check read
    # the same documents and did not, so one escaping citation was a blocker in one tool and
    # support in the other, and the number it carried read as sourced to whichever tool the reader
    # happened to run. These pin the refusal in check, at blocker, by all three ways out of a tree:
    # a relative climb, an absolute path, and a symlink standing inside the repository and pointing
    # out of it. The last one is the reason the lexical test alone is not enough, because ../ and a
    # leading slash are both visible in the citation text and a symlink is not.

    SOURCE = "RETENTION_DAYS = 2555\n"
    CLAIM = "Request logs are retained for 2555 days\n[`%s`].\n"

    def setUp(self):
        self.check = load("docdna_check", CHECK_PATH)

    def base(self, tmp):
        # macOS hands out a temporary directory behind a symlinked /var, and this class asks what
        # a symlink does to containment. Resolving the base first keeps the symlink under test the
        # only one in the path.
        return Path(os.path.realpath(str(tmp)))

    def neighbour(self, tmp, name="outside"):
        # A real file one level above the repository. Without a neighbour to reach, an escape test
        # proves only that a missing file is missing.
        outside = self.base(tmp) / name
        outside.mkdir(parents=True, exist_ok=True)
        path = outside / "secrets.py"
        path.write_text(self.SOURCE, encoding="utf-8")
        return path

    def run_check(self, root, cited, extra=None):
        tree = {"src/config/settings.py": SETTINGS,
                "docs/build/config-reference.md": document(self.CLAIM % cited)}
        tree.update(extra or {})
        write_repo(root, tree)
        report = self.check.check(str(root), set(self.check.PASSES), "major", None, False)
        return report["findings"]

    def findings(self, tmp, cited, extra=None, symlink=None, symlink_to=None):
        outside = self.neighbour(tmp)
        repo = self.base(tmp) / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        if symlink:
            link = repo / symlink
            link.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(str(repo / symlink_to) if symlink_to else str(outside), str(link))
        return self.run_check(repo, cited, extra)

    def test_check_refuses_a_code_citation_that_climbs_out_of_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = self.findings(tmp, "../outside/secrets.py#RETENTION_DAYS")
            rows = kinds(found, "path-outside-repo")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "blocker")
            self.assertIn("../outside/secrets.py", rows[0]["detail"])
            self.assertIn("does not resolve inside the repository", rows[0]["detail"])
            # The refusal has to reach the number as well as the path. A citation rejected and
            # still counted as support would leave 2555 reading as sourced.
            numbers = kinds(found, "generated-number")
            self.assertEqual(len(numbers), 1)
            self.assertIn("2555", numbers[0]["detail"])

    def test_check_refuses_a_code_citation_that_names_an_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = self.neighbour(tmp)
            self.assertTrue(os.path.isabs(str(outside)))
            found = self.findings(tmp, "%s#RETENTION_DAYS" % outside)
            rows = kinds(found, "path-outside-repo")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "blocker")
            self.assertIn(str(outside), rows[0]["detail"])
            self.assertIn("names an absolute location", rows[0]["detail"])
            numbers = kinds(found, "generated-number")
            self.assertEqual(len(numbers), 1)
            self.assertIn("2555", numbers[0]["detail"])

    def test_check_refuses_a_code_citation_that_leaves_through_a_symlink(self):
        # The citation text here is an ordinary in-repo relative path and reads as clean. Only
        # resolving it finds the escape, which is why the lexical clause cannot carry this alone.
        with tempfile.TemporaryDirectory() as tmp:
            found = self.findings(tmp, "src/config/linked.py#RETENTION_DAYS",
                                  symlink="src/config/linked.py")
            rows = kinds(found, "path-outside-repo")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "blocker")
            self.assertIn("src/config/linked.py", rows[0]["detail"])
            self.assertNotIn("..", rows[0]["detail"].split(" does not")[0])
            numbers = kinds(found, "generated-number")
            self.assertEqual(len(numbers), 1)
            self.assertIn("2555", numbers[0]["detail"])

    def test_check_refuses_a_neighbour_whose_directory_name_extends_the_repository_name(self):
        # contained() compares on a separator rather than on a bare prefix. Without the separator,
        # <tmp>/repo-notes reads as inside <tmp>/repo, and every sibling directory whose name
        # begins with the repository's name becomes citable evidence. The repository a user checks
        # out beside its own notes directory is the ordinary case, not a contrived one.
        with tempfile.TemporaryDirectory() as tmp:
            outside = self.neighbour(tmp, "repo-notes")
            repo = self.base(tmp) / "repo"
            self.assertTrue(str(outside).startswith(str(repo)),
                            "the neighbour no longer shares a prefix with the repository")
            found = self.run_check(repo, "../repo-notes/secrets.py#RETENTION_DAYS")
            rows = kinds(found, "path-outside-repo")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "blocker")
            self.assertIn("../repo-notes/secrets.py", rows[0]["detail"])
            self.assertEqual(len(kinds(found, "generated-number")), 1)

    def test_check_refuses_a_citation_that_leaves_and_re_enters_by_the_real_path(self):
        # The reason inside_repo reads the path twice. Here the repository is reached through a
        # symlinked parent, so the citation climbs out of the tree the user named and comes back in
        # by the physical one. The resolved clause alone says this is inside and accepts it, which
        # binds a number through a path that resolves to a different file, or to nothing, on any
        # machine checking the repository out elsewhere. Only the lexical clause refuses it.
        with tempfile.TemporaryDirectory() as tmp:
            base = self.base(tmp)
            (base / "store").mkdir()
            os.symlink(str(base / "store"), str(base / "work"))
            root = base / "work" / "repo"
            cited = "../../store/repo/src/config/retention.py#RETENTION_DAYS"
            found = self.run_check(root, cited, {"src/config/retention.py": self.SOURCE})
            rows = kinds(found, "path-outside-repo")

            self.assertNotEqual(os.path.abspath(str(root)), os.path.realpath(str(root)),
                                "the repository is no longer reached through a symlink")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["severity"], "blocker")
            self.assertIn("../../store/repo", rows[0]["detail"])
            self.assertEqual(len(kinds(found, "generated-number")), 1)

    def test_a_legitimate_in_repo_citation_still_resolves_in_check(self):
        # The control for the three above. A guard that refused every code citation, or refused
        # every symlink, would pass all three and make the citation class useless. Both shapes are
        # checked: a plain in-repo file, and a symlink that stays inside the tree.
        with tempfile.TemporaryDirectory() as tmp:
            found = self.findings(tmp, "src/config/retention.py#RETENTION_DAYS",
                                  extra={"src/config/retention.py": "RETENTION_DAYS = 2555\n"})

            self.assertEqual(kinds(found, "path-outside-repo"), [])
            self.assertEqual(kinds(found, "generated-number"), [])
            self.assertEqual(kinds(found, "stale-evidence"), [])

    def test_a_symlink_that_points_back_inside_the_repository_still_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = self.findings(tmp, "src/config/linked.py#RETENTION_DAYS",
                                  extra={"src/config/retention.py": "RETENTION_DAYS = 2555\n"},
                                  symlink="src/config/linked.py",
                                  symlink_to="src/config/retention.py")

            self.assertEqual(kinds(found, "path-outside-repo"), [])
            self.assertEqual(kinds(found, "generated-number"), [])
            self.assertEqual(kinds(found, "stale-evidence"), [])


class CodednaAdoptionRegressionTests(unittest.TestCase):
    # A repository that already carries CODEDNA.md owns a written coding standard, and the catalog
    # has to read that file as the document rather than report the standard missing and ask for a
    # second one beside it. The other half costs more and is the one worth pinning: a repository
    # with no CODEDNA.md must not learn the word from the catalog. detect_paths is how the catalog
    # recognises a document, not a recommendation, and a manifest that names a file the repository
    # does not have reads as docdna advertising a tool the project never chose.

    STANDARD = "build.coding-standard"
    TREE = {"README.md": "# app\n\nA small service.\n",
            "pyproject.toml": "[project]\nname = \"app\"\n",
            "src/config/settings.py": SETTINGS}

    def setUp(self):
        self.select = load("docdna_select", SELECT_PATH)

    def manifest(self, tmp, extra=None):
        tree = dict(self.TREE)
        tree.update(extra or {})
        repo = write_repo(Path(tmp) / "repo", tree)
        manifest, report = self.select.select(str(repo), None, None, True)
        return manifest, report

    def row(self, manifest):
        rows = [item for item in manifest["documents"] if item["id"] == self.STANDARD]
        self.assertEqual(len(rows), 1, "%s is not in the manifest" % self.STANDARD)
        return rows[0]

    def test_a_repository_carrying_codedna_md_has_it_adopted_as_the_coding_standard(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, _ = self.manifest(tmp, {"CODEDNA.md": "# Code DNA\n\nHouse style.\n"})
            row = self.row(manifest)

            self.assertEqual(row["found_at"], "CODEDNA.md")
            self.assertNotEqual(row["state"], "absent")
            self.assertTrue(row["state"].startswith("present"), row["state"])

    def test_the_same_repository_without_codedna_md_reports_the_standard_absent(self):
        # The control. A row that read present whatever the tree held would pass the test above
        # without CODEDNA.md ever being looked for.
        with tempfile.TemporaryDirectory() as tmp:
            manifest, _ = self.manifest(tmp)
            row = self.row(manifest)

            self.assertIsNone(row["found_at"])
            self.assertEqual(row["state"], "absent")

    def test_a_manifest_for_a_repository_without_codedna_md_never_mentions_codedna(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, report = self.manifest(tmp)
            blob = json.dumps(manifest, sort_keys=True)

            self.assertNotIn("codedna", blob.lower())
            self.assertNotIn("codedna", report.lower())
            # The manifest is not empty of the row that carries the risk, so the assertion above
            # is a statement about content rather than about an absent document.
            self.assertEqual(self.row(manifest)["path"], "docs/build/coding-standard.md")


if __name__ == "__main__":
    unittest.main()
