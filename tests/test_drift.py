"""Drift detection: which manifest answers for a command, which paths exist, what is a path."""

import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_PATH = ROOT / "skill" / "scripts" / "docdna_scan.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
GIT = shutil.which("git")

COMMAND_DOC = "# %s\n\n```sh\n%s\n```\n"

PACKAGE_LINT_ONLY = """{
  "name": "root",
  "scripts": {"lint": "eslint"}
}
"""

PYPROJECT_ROOT = """[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "devtools"
version = "0.1.0"

[project.scripts]
devtools = "devtools.cli:main"
"""

PYPROJECT_NAMED = """[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "%s"
version = "0.1.0"
"""

PYPROJECT_WITH_ENTRY = PYPROJECT_NAMED + """
[project.scripts]
%s = "%s.cli:main"
"""

IGNORE_RULES = ".env\n.env.*\nnode_modules/\ndist/\n"

IGNORE_README = """# secrets

Copy the keys into `src/.env.local` before starting.

Production keys go in `src/.env.production`, which nobody commits.

The removed helper is `src/legacy.js`.
"""


def load_scan():
    spec = importlib.util.spec_from_file_location("docdna_scan", SCAN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(root, rel, body):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def git(root, *args):
    subprocess.run(["git", "-C", str(root)] + list(args), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# The committed fixtures are the clean case: every command they document resolves and every path
# they name is right. A drifted document has to be added to one to see a finding, and adding it to
# the tree in the repository would change what every other fixture-walking test sees, so the tree
# is copied and the drifted documents are written into the copy.
def copy_fixture(tmp, name, extra=None):
    dest = Path(tmp) / name
    shutil.copytree(str(FIXTURES / name), str(dest))
    for rel, body in (extra or {}).items():
        write(dest, rel, body)
    return dest


def index_ctx(scan, root):
    index = scan.build_index(str(root))
    return {"root": str(root), "pathset": index["pathset"], "dirs": index["dirs"],
            "listings": {}}


def rows_of(report, kind=None, doc=None):
    rows = report["drift"]
    if kind is not None:
        rows = [row for row in rows if row["kind"] == kind]
    if doc is not None:
        rows = [row for row in rows if row["doc"] == doc]
    return rows


def claims(report, kind=None, doc=None):
    return sorted(row["claim"] for row in rows_of(report, kind, doc))


class ManifestResolutionTests(unittest.TestCase):
    def setUp(self):
        self.scan = load_scan()

    def scan_monorepo(self, tmp, extra=None):
        return self.scan.scan(str(copy_fixture(tmp, "monorepo", extra)), set(), False, 5)

    def python_workspaces(self, tmp, extra=None):
        write(tmp, "pyproject.toml", PYPROJECT_ROOT)
        write(tmp, "README.md", COMMAND_DOC % ("devtools", "devtools scan"))
        write(tmp, "packages/api/pyproject.toml",
              PYPROJECT_WITH_ENTRY % ("apitool", "apitool", "apitool"))
        write(tmp, "packages/api/README.md", COMMAND_DOC % ("apitool", "apitool run"))
        write(tmp, "packages/devtools/pyproject.toml", PYPROJECT_NAMED % "devtools")
        write(tmp, "packages/ghost/pyproject.toml", PYPROJECT_NAMED % "ghosttool")
        for rel, body in (extra or {}).items():
            write(tmp, rel, body)
        return self.scan.scan(str(tmp), set(), False, 5)

    # Five root commands, four manifests holding a `build` script between them. A scanner that
    # keeps one package.json for the whole repository checks the root README against whichever it
    # met first, and `test:llm-output` is declared only at the root.
    def test_a_root_document_claiming_a_root_script_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_monorepo(tmp)

            self.assertEqual(rows_of(report, "command-not-found", "README.md"), [])
            self.assertEqual(rows_of(report), [])

    def test_a_workspace_document_claiming_its_own_script_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_monorepo(tmp)

            self.assertEqual(rows_of(report, "command-not-found", "apps/web/README.md"), [])
            self.assertEqual(rows_of(report, "command-not-found", "apps/api/README.md"), [])

    # `release:package` is declared at the root and nowhere else. A reader in apps/web who runs it
    # gets "script not found", because bun reads the package.json in the directory it is run from,
    # so this is a real finding. It is a weak one: the script exists, the document is in the wrong
    # place, and the row says which manifest declares it. The row that says the script exists
    # nowhere at all is a stronger reading of the same tree, and it reports at the same confidence,
    # because 51 repositories of hand adjudication put the stronger reading at 0 of 27 true. What
    # separates the two cases is `detail`, which states what was read, not `confidence`, which
    # would state what to believe.
    def test_a_workspace_document_claiming_a_root_only_script_is_a_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_monorepo(tmp, {
                "apps/web/release.md": COMMAND_DOC % ("release", "bun run release:package")})
            rows = rows_of(report, "command-not-found", "apps/web/release.md")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["claim"], "bun run release:package")
            self.assertEqual(rows[0]["confidence"], "low")
            self.assertEqual(rows[0]["checked_against"], "package.json:scripts")
            self.assertIn("declared in package.json", rows[0]["detail"])
            self.assertIn("not in apps/web/package.json", rows[0]["detail"])

    def test_a_script_declared_nowhere_is_a_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_monorepo(tmp, {
                "apps/web/ghost.md": COMMAND_DOC % ("ghost", "bun run typecheck")})
            rows = rows_of(report, "command-not-found", "apps/web/ghost.md")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["claim"], "bun run typecheck")
            self.assertEqual(rows[0]["confidence"], self.scan.COMMAND_CONFIDENCE)
            self.assertEqual(rows[0]["precision_note"], self.scan.COMMAND_PRECISION_NOTE)
            self.assertEqual(rows[0]["checked_against"], "apps/web/package.json:scripts")
            self.assertIn("no `typecheck` script", rows[0]["detail"])

    def test_a_root_document_claiming_a_root_target_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_monorepo(tmp)

            self.assertEqual(rows_of(report, "command-not-found", "README.md"), [])

    def test_a_workspace_document_claiming_its_own_target_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_monorepo(tmp)

            self.assertEqual(
                rows_of(report, "command-not-found", "packages/shared/README.md"), [])

    def test_a_workspace_document_claiming_a_root_only_target_is_a_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_monorepo(tmp, {
                "packages/shared/deploy.md": COMMAND_DOC % ("deploy", "make deploy")})
            rows = rows_of(report, "command-not-found", "packages/shared/deploy.md")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["claim"], "make deploy")
            self.assertEqual(rows[0]["confidence"], "low")
            self.assertEqual(rows[0]["checked_against"], "Makefile:targets")
            self.assertIn("declared in Makefile", rows[0]["detail"])
            self.assertIn("not in packages/shared/Makefile", rows[0]["detail"])

    def test_a_target_declared_nowhere_is_a_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_monorepo(tmp, {
                "packages/shared/ghost.md": COMMAND_DOC % ("ghost", "make package")})
            rows = rows_of(report, "command-not-found", "packages/shared/ghost.md")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["claim"], "make package")
            self.assertEqual(rows[0]["confidence"], self.scan.COMMAND_CONFIDENCE)
            self.assertEqual(rows[0]["precision_note"], self.scan.COMMAND_PRECISION_NOTE)
            self.assertEqual(rows[0]["checked_against"], "packages/shared/Makefile:targets")
            self.assertIn("no `package` target", rows[0]["detail"])

    def test_a_root_document_claiming_a_root_entry_point_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.python_workspaces(tmp)

            self.assertEqual(rows_of(report, "command-not-found", "README.md"), [])

    def test_a_workspace_document_claiming_its_own_entry_point_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.python_workspaces(tmp)

            self.assertEqual(
                rows_of(report, "command-not-found", "packages/api/README.md"), [])

    # packages/devtools declares the distribution and the root still declares the console script.
    # Installing packages/devtools alone does not put `devtools` on the path, so the command in its
    # README fails, and the row points at the manifest that does declare it.
    def test_a_workspace_document_claiming_a_root_only_entry_point_is_a_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.python_workspaces(tmp, {
                "packages/devtools/README.md": COMMAND_DOC % ("serve", "devtools serve")})
            rows = rows_of(report, "command-not-found", "packages/devtools/README.md")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["claim"], "devtools serve")
            self.assertEqual(rows[0]["confidence"], "low")
            self.assertEqual(rows[0]["checked_against"], "pyproject.toml:project.scripts")
            self.assertIn("declared in pyproject.toml", rows[0]["detail"])
            self.assertIn("not in packages/devtools/pyproject.toml", rows[0]["detail"])

    def test_an_entry_point_declared_nowhere_is_a_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.python_workspaces(tmp, {
                "packages/ghost/README.md": COMMAND_DOC % ("ghost", "ghosttool build")})
            rows = rows_of(report, "command-not-found", "packages/ghost/README.md")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["claim"], "ghosttool build")
            self.assertEqual(rows[0]["confidence"], self.scan.COMMAND_CONFIDENCE)
            self.assertEqual(rows[0]["precision_note"], self.scan.COMMAND_PRECISION_NOTE)
            self.assertEqual(rows[0]["checked_against"],
                             "packages/ghost/pyproject.toml:project.scripts")
            self.assertIn("no console script named `ghosttool`", rows[0]["detail"])
            self.assertNotIn("resolution_note", rows[0])

    # A pyproject entry point and a setup.py entry point used to differ by confidence, because a
    # regex reading of setup.py is a reading of the source and not of the list an install produces.
    # That is a fact about how the name was resolved, so it survives the demotion as a note on the
    # row rather than as a number that ranks one lead above another.
    def test_a_setup_py_entry_point_carries_the_build_time_note_at_the_same_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "setup.py", "setup(name=\"oldtool\")\n")
            write(tmp, "README.md", COMMAND_DOC % ("oldtool", "oldtool build"))
            report = self.scan.scan(str(tmp), set(), False, 5)
            rows = rows_of(report, "command-not-found", "README.md")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["confidence"], self.scan.COMMAND_CONFIDENCE)
            self.assertEqual(rows[0]["precision_note"], self.scan.COMMAND_PRECISION_NOTE)
            self.assertEqual(rows[0]["resolution_note"], self.scan.SETUP_PY_NOTE)

    # The whole point of the demotion. Every runtime, every resolution, one confidence, and it is
    # the same one every path finding already carries. A field that ranked these rows against each
    # other was wrong 27 times out of 27, which is worse than having no field.
    def test_no_command_finding_outranks_another(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_monorepo(tmp, {
                "apps/web/release.md": COMMAND_DOC % ("release", "bun run release:package"),
                "apps/web/ghost.md": COMMAND_DOC % ("ghost", "bun run typecheck"),
                "packages/shared/deploy.md": COMMAND_DOC % ("deploy", "make deploy"),
                "packages/shared/ghost.md": COMMAND_DOC % ("ghost", "make package")})
            rows = rows_of(report, "command-not-found")

            self.assertEqual(len(rows), 4)
            self.assertEqual(set(row["confidence"] for row in rows), {"low"})
            self.assertEqual(set(row["precision_note"] for row in rows),
                             {self.scan.COMMAND_PRECISION_NOTE})

    # The order is the whole rule. Nearest first, root last, and nothing off the chain: a document
    # in apps/web is never answered by the manifest in apps/api.
    def test_the_manifest_chain_runs_from_the_document_to_the_root(self):
        byfolder = {"": {"path": "package.json"},
                    "apps/api": {"path": "apps/api/package.json"},
                    "apps/web": {"path": "apps/web/package.json"}}

        self.assertEqual([entry["path"] for entry in
                          self.scan.manifest_chain(byfolder, "apps/web/README.md")],
                         ["apps/web/package.json", "package.json"])
        self.assertEqual([entry["path"] for entry in
                          self.scan.manifest_chain(byfolder, "README.md")],
                         ["package.json"])
        self.assertEqual([entry["path"] for entry in
                          self.scan.manifest_chain(byfolder, "packages/shared/README.md")],
                         ["package.json"])
        self.assertEqual(self.scan.manifest_chain({}, "README.md"), [])


# A command finding says a name is not in a manifest. It used to say what would happen next, and
# what would happen next was not checked. Every case below was decided by running the command and
# reading the exit code, and the tool versions are named because a fallback is a behaviour of a
# tool rather than a fact about a repository.
class CommandConsequenceTests(unittest.TestCase):
    def setUp(self):
        self.scan = load_scan()

    def scan_tree(self, tmp, files):
        for rel, body in files.items():
            write(tmp, rel, body)
        return self.scan.scan(str(tmp), set(), False, 5)

    def details(self, report):
        return [row["detail"] for row in rows_of(report, "command-not-found")]

    # The rule that used to live here read a missing [build-system] table as a broken editable
    # install. Run on 2026-08-01: a venv holding pip 25.3 and nothing else, a tree whose
    # pyproject.toml declares [project] and no [build-system], `pip install -e ".[dev]"
    # --no-deps` exits 0 and the package imports. PEP 517 falls back to
    # setuptools.build_meta:__legacy__ for exactly this shape, so the absence of the table is
    # ordinary and there is nothing to report.
    def test_an_editable_install_without_a_build_system_table_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "pyproject.toml": "[project]\nname = \"thing\"\nversion = \"0.1.0\"\n",
                "src/thing/__init__.py": "VERSION = \"0.1.0\"\n",
                "README.md": COMMAND_DOC % ("install",
                                            "pip install -e .\npip install -e \".[dev]\"")})

            self.assertEqual(rows_of(report, "command-not-found"), [])
            self.assertFalse(hasattr(self.scan, "editable_drift"))
            self.assertFalse(hasattr(self.scan, "BUILD_SYSTEM"))

    # GNU Make 3.81: a Makefile whose whole content is `include extra.mk`, with `server:` in
    # extra.mk, runs `make server`. The included file is read with the including one.
    def test_a_target_from_an_included_makefile_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "Makefile": "include extra.mk\n\nbuild:\n\t@echo build\n",
                "extra.mk": "server:\n\t@echo server\n",
                "README.md": COMMAND_DOC % ("run", "make server")})

            self.assertEqual(rows_of(report, "command-not-found"), [])

    # An include the scanner cannot resolve leaves the rule set half read, and a target absent from
    # half a rule set is absent from a partial reading, not from the makefile.
    def test_a_makefile_with_an_unreadable_include_reports_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "Makefile": "include $(wildcard mk/*.mk)\n\nbuild:\n\t@echo build\n",
                "README.md": COMMAND_DOC % ("run", "make ghost")})

            self.assertEqual(rows_of(report, "command-not-found"), [])

    # GNU Make 3.81: `%.pdf: %.md` plus paper.md builds paper.pdf with no rule named paper.pdf,
    # and `make foo.o` compiles foo.c through a built-in suffix rule the makefile never mentions.
    def test_a_name_a_rule_can_produce_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "Makefile": "build:\n\t@echo build\n\n%.pdf: %.md\n\t@echo pdf\n",
                "paper.md": "paper\n",
                "foo.c": "int main(void){return 0;}\n",
                "README.md": COMMAND_DOC % ("run", "make paper.pdf\nmake foo.o\nmake README.md")})

            self.assertEqual(rows_of(report, "command-not-found"), [])

    # `make README.md` on a file that is on disk with no rule for it exits 0 with "Nothing to be
    # done", and so does `make docs` on a directory. Covered above for the file; here for the
    # directory, and for the name that really has no rule anywhere.
    def test_a_name_no_rule_can_produce_is_reported_as_an_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "Makefile": "build:\n\t@echo build\n",
                "docs/index.md": "# docs\n",
                "README.md": COMMAND_DOC % ("run", "make docs\nmake ghost")})
            rows = rows_of(report, "command-not-found")

            self.assertEqual([row["claim"] for row in rows], ["make ghost"])
            self.assertEqual(rows[0]["detail"],
                             "no `ghost` target in Makefile; targets are build")

    # `make -C sidecar test` is a claim about sidecar/Makefile. The makefile nearest the document
    # never sees the command, so it cannot answer for it either way.
    def test_a_sub_makefile_invoked_with_dash_c_answers_for_the_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "Makefile": "build:\n\t@echo build\n",
                "sidecar/Makefile": "test:\n\t@echo test\n",
                "README.md": COMMAND_DOC % ("run", "make -C sidecar test\nmake -C sidecar ghost")})
            rows = rows_of(report, "command-not-found")

            self.assertEqual([row["claim"] for row in rows], ["make -C sidecar ghost"])
            self.assertEqual(rows[0]["checked_against"], "sidecar/Makefile:targets")
            self.assertIn("no `ghost` target in sidecar/Makefile", rows[0]["detail"])

    # A flag argument, a command-line variable and another makefile each used to be read as the
    # target name, which reported a finding about a word nobody typed as a target.
    def test_a_flag_or_a_variable_is_not_read_as_a_target(self):
        self.assertEqual(self.scan.make_invocation("make -j4 build"), ("build", None))
        self.assertEqual(self.scan.make_invocation("make -j 4 build"), ("build", None))
        self.assertEqual(self.scan.make_invocation("make PREFIX=/usr build"), ("build", None))
        self.assertEqual(self.scan.make_invocation("make -C sub test"), ("test", "sub"))
        self.assertEqual(self.scan.make_invocation("make --directory=sub test"), ("test", "sub"))
        self.assertIsNone(self.scan.make_invocation("make -f other.mk ghost"))
        self.assertIsNone(self.scan.make_invocation("make"))

        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "Makefile": "build:\n\t@echo build\n",
                "README.md": COMMAND_DOC % (
                    "run", "make -j4 build\nmake -j 4 build\nmake PREFIX=/usr build\n"
                           "make -f other.mk ghost")})

            self.assertEqual(rows_of(report, "command-not-found"), [])

    # `build test:` declares two targets. Reading the left side up to the first space declared
    # neither of them, and both then read as missing.
    def test_several_targets_on_one_rule_line_are_all_declared(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "Makefile": "build test:\n\t@echo both\n\nlint:: \n\t@echo lint\n",
                "README.md": COMMAND_DOC % ("run", "make build\nmake test\nmake lint")})

            self.assertEqual(rows_of(report, "command-not-found"), [])

    # npm 10.9.8: `npm run build --workspaces` at a root with no `build` script exits 0 and runs
    # the workspace's script, and `npm run ghost --if-present` exits 0 with no script at all. The
    # scripts table of the manifest nearest the document does not decide either one.
    def test_a_delegating_or_optional_invocation_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "package.json": PACKAGE_LINT_ONLY,
                "README.md": COMMAND_DOC % (
                    "run", "npm run build --workspaces\nnpm run build -w packages/web\n"
                           "npm run ghost --if-present\npnpm -r build\npnpm --filter web build\n"
                           "yarn workspace web build")})

            self.assertEqual(rows_of(report, "command-not-found"), [])

    # yarn 1.22.22 and bun 1.3.11 run a name that is not a script as a binary from
    # node_modules/.bin, and bun takes one from PATH as well; npm 10.9.8 and pnpm 11.15.1 exit 1.
    # node_modules is not committed, so the row reports the manifest and says what it did not read.
    def test_a_yarn_or_bun_row_records_the_binary_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "package.json": PACKAGE_LINT_ONLY,
                "README.md": COMMAND_DOC % (
                    "run", "npm run dev\npnpm run dev\nyarn dev\nbun run dev")})
            notes = dict((row["claim"], row.get("resolution_note"))
                         for row in rows_of(report, "command-not-found"))

            self.assertEqual(sorted(notes),
                             ["bun run dev", "npm run dev", "pnpm run dev", "yarn dev"])
            self.assertIsNone(notes["npm run dev"])
            self.assertIsNone(notes["pnpm run dev"])
            self.assertEqual(notes["yarn dev"], self.scan.BIN_FALLBACK_NOTE)
            self.assertEqual(notes["bun run dev"], self.scan.BIN_FALLBACK_NOTE)
            self.assertEqual(self.details(report)[0],
                             "no `dev` script in package.json; scripts are lint")

    # The count comes from the paths an OpenAPI document declares, and the row says so. When it
    # comes from the route pattern instead it is a count of matching lines, which is not a count of
    # routes, and the row is not allowed to call it one.
    def test_a_count_row_says_what_was_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "openapi.yaml": "openapi: 3.0.0\npaths:\n  /orders:\n  /orders/{id}:\n",
                "README.md": "# api\n\nThe service exposes 9 endpoints today.\n"})
            rows = rows_of(report, "count-mismatch")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["claim"], "9 endpoints")
            self.assertEqual(rows[0]["detail"], "2 paths declared in openapi.yaml")
            self.assertEqual(self.scan.PATTERN_COUNT,
                             "lines matched by the iface.http route pattern")

    # The rule for the whole file: a detail says what was read, and stops. A tree that fires the
    # node, make, python, cargo, go and process rules at once, checked against the vocabulary of
    # consequence that the [build-system] detail used to be written in.
    def test_no_command_detail_asserts_a_consequence(self):
        forbidden = re.compile(r"(?i)\b(fails?|failing|failed|breaks?|broken|error|errors|"
                               r"unavailable|invalid|will not|won't|cannot|can't|would|should)\b")
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "package.json": PACKAGE_LINT_ONLY,
                "Makefile": "build:\n\t@echo build\n",
                "pyproject.toml": "[project]\nname = \"thing\"\nversion = \"0.1.0\"\n",
                "Cargo.toml": "[package]\nname = \"engine\"\nversion = \"0.1.0\"\n",
                "go.mod": "module example.com/app\n\ngo 1.21\n",
                "Procfile": "web: gunicorn app.wsgi\n",
                "README.md": COMMAND_DOC % (
                    "run", "npm run dev\nmake ghost\nthing serve\ncargo run --bin ghost\n"
                           "go run ./cmd/ghost\npython manage.py runserver")})
            details = self.details(report)

            self.assertEqual(len(details), 6)
            for detail in details:
                self.assertIsNone(forbidden.search(detail), detail)


class PathExistenceTests(unittest.TestCase):
    def setUp(self):
        self.scan = load_scan()

    # A repository that ignores its environment files and its bundle output. src/.env.local is on
    # disk and out of the index; src/.env.production is in neither; src/legacy.js is ignored by
    # nothing and absent from both, which is the only broken reference here.
    def ignoring_repo(self, tmp):
        write(tmp, ".gitignore", IGNORE_RULES)
        write(tmp, "src/.env.local", "TOKEN=local\n")
        write(tmp, "src/app.js", "console.log(1)\n")
        write(tmp, "README.md", IGNORE_README)
        git(tmp, "init", "--quiet")
        git(tmp, "add", "-A")
        git(tmp, "-c", "user.email=t@example.com", "-c", "user.name=t",
            "commit", "--quiet", "-m", "init")
        return self.scan.scan(str(tmp), set(), False, 5)

    @unittest.skipUnless(GIT, "git is not installed")
    def test_a_gitignored_path_that_exists_on_disk_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.ignoring_repo(tmp)
            ctx = index_ctx(self.scan, tmp)

            self.assertNotIn("src/.env.local", claims(report))
            self.assertIsNone(self.scan.resolve_path(ctx, "", "src/.env.local"))
            self.assertEqual(self.scan.resolve_disk(ctx, "", "src/.env.local"),
                             "src/.env.local")

    @unittest.skipUnless(GIT, "git is not installed")
    def test_a_gitignored_path_that_does_not_exist_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.ignoring_repo(tmp)
            ctx = index_ctx(self.scan, tmp)

            self.assertNotIn("src/.env.production", claims(report))
            self.assertIsNone(self.scan.resolve_disk(ctx, "", "src/.env.production"))
            self.assertEqual(report["scan"]["ignore_source"], "git")
            self.assertEqual(report["scan"]["ignore_unchecked"], 0)

    @unittest.skipUnless(GIT, "git is not installed")
    def test_a_tracked_path_that_does_not_exist_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.ignoring_repo(tmp)
            rows = rows_of(report, "path-not-found")

            self.assertEqual([row["claim"] for row in rows], ["src/legacy.js"])
            self.assertEqual(rows[0]["confidence"], "low")
            self.assertEqual(rows[0]["precision_note"], self.scan.PATH_PRECISION_NOTE)
            self.assertEqual(rows[0]["checked_against"], "working tree")

    # The committed fixture, scanned where it lives. web/.env.local, web/node_modules and web/dist
    # are all named on purpose and all ignored; web/src/onboarding.js is the one stale link.
    @unittest.skipUnless(GIT, "git is not installed")
    def test_the_gitignored_fixture_reports_only_its_stale_link(self):
        report = self.scan.scan(str(FIXTURES / "gitignored_paths"), set(), False, 5)

        self.assertEqual(report["scan"]["ignore_source"], "git")
        self.assertEqual(claims(report, "path-not-found"), ["web/src/onboarding.js"])
        self.assertEqual(report["inventory"]["counts"]["broken_links"], 1)

    # A dot directory is pruned out of the file index and is still on disk. The index decides what
    # docdna reads; the filesystem decides what exists.
    def test_a_path_pruned_from_the_index_but_present_on_disk_is_not_reported(self):
        root = FIXTURES / "gitignored_paths"
        report = self.scan.scan(str(root), set(), False, 5)
        ctx = index_ctx(self.scan, root)

        self.assertNotIn("web/.godplans/PLAN.md", claims(report))
        self.assertIsNone(self.scan.resolve_path(ctx, "", "web/.godplans/PLAN.md"))
        self.assertEqual(self.scan.resolve_disk(ctx, "", "web/.godplans/PLAN.md"),
                         "web/.godplans/PLAN.md")

    # os.path.exists answers without regard to case on macOS and Windows, so it says src/handler.py
    # is there in a tree that only holds src/Handler.py. Comparing every component against the real
    # directory listing gives the same answer on both kinds of filesystem, which is what makes this
    # test mean the same thing everywhere it runs.
    def test_a_case_mismatched_path_is_reported_on_any_filesystem(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "src/Handler.py", "def handle():\n    return 1\n")
            write(tmp, "README.md", "The entry point is `src/handler.py`.\n")
            report = self.scan.scan(str(tmp), set(), False, 5)
            ctx = index_ctx(self.scan, tmp)
            rows = rows_of(report, "path-not-found")
            kind = ("case-insensitive"
                    if os.path.exists(os.path.join(tmp, "src", "handler.py"))
                    else "case-sensitive")

            self.assertEqual([row["claim"] for row in rows], ["src/handler.py"])
            self.assertEqual(rows[0]["confidence"], "low")
            self.assertFalse(self.scan.disk_entry(ctx, "src/handler.py"),
                             "the wrong case was accepted on a %s filesystem" % kind)
            self.assertTrue(self.scan.disk_entry(ctx, "src/Handler.py"),
                            "the right case was refused on a %s filesystem" % kind)

    # Without git there is no authority on what is ignored, so the scanner guesses from a list of
    # names. build, dist, out and target are ordinary English words that only mean "generated" at
    # the top of a project. docs/build is where docdna writes its own output, and a guess that
    # matched the word at any depth would silence every finding in it.
    def test_the_narrow_fallback_still_reports_a_missing_docs_build_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "docs/build/index.md", "# build stage\n")
            write(tmp, "README.md", "See [config](docs/build/config.md).\n")
            report = self.scan.scan(str(tmp), set(), False, 5)
            rows = rows_of(report, "path-not-found")

            self.assertFalse(os.path.exists(os.path.join(tmp, ".git")))
            self.assertEqual(report["scan"]["ignore_source"], "builtin")
            self.assertEqual(report["scan"]["ignore_fallback"], "no git repository")
            self.assertEqual([row["claim"] for row in rows], ["docs/build/config.md"])
            self.assertEqual(rows[0]["confidence"], "low")

    def test_the_fallback_names_match_generated_roots_only_at_the_top(self):
        self.assertTrue(self.scan.builtin_ignored("build/out.js"))
        self.assertTrue(self.scan.builtin_ignored("dist/bundle.js"))
        self.assertFalse(self.scan.builtin_ignored("docs/build/config.md"))
        self.assertFalse(self.scan.builtin_ignored("web/dist"))
        self.assertTrue(self.scan.builtin_ignored("web/node_modules"))
        self.assertTrue(self.scan.builtin_ignored("apps/web/__pycache__/app.pyc"))
        self.assertTrue(self.scan.builtin_ignored("src/.env.production"))
        self.assertTrue(self.scan.builtin_ignored("config/prod.env"))
        self.assertFalse(self.scan.builtin_ignored("src/.envoy"))


class TokenExtractionTests(unittest.TestCase):
    def setUp(self):
        self.scan = load_scan()

    def scan_tree(self, tmp, files):
        for rel, body in files.items():
            write(tmp, rel, body)
        return self.scan.scan(str(tmp), set(), False, 5)

    # A leading dot belongs to the name. Stripping it invents a path that was never referenced,
    # and then reports that invention missing.
    def test_a_leading_dot_stays_part_of_the_path(self):
        self.assertEqual(self.scan.path_candidate(".deploy/app"), ".deploy/app")
        self.assertEqual(self.scan.path_candidate(".eslintrc.json"), ".eslintrc.json")
        self.assertEqual(self.scan.path_candidate(".github/workflows/ci.yml"),
                         ".github/workflows/ci.yml")
        self.assertEqual(self.scan.path_candidate(".deploy/app,"), ".deploy/app")

        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "src/app.js": "console.log(1)\n",
                "README.md": "Lint rules live in [.eslintrc.json](.eslintrc.json).\n"})
            rows = rows_of(report, "path-not-found")

            self.assertEqual([row["claim"] for row in rows], [".eslintrc.json"])

    def test_a_fragment_selects_a_symbol_not_a_filename(self):
        self.assertEqual(self.scan.path_candidate("lib/foo.js#listPacks"), "lib/foo.js")

        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "lib/foo.js": "export const listPacks = () => []\n",
                "README.md": "The list comes from `lib/foo.js#listPacks`.\n"})

            self.assertEqual(rows_of(report, "path-not-found"), [])

    # Every language resolves a module specifier by searching extensions, so a reference written
    # without one is a reference to the file the search finds.
    def test_an_extensionless_module_specifier_resolves_to_its_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "lib/drift-detector.js": "export const detect = () => []\n",
                "lib/loader/index.js": "export const load = () => []\n",
                "README.md": "Drift lives in `lib/drift-detector` and loading in `lib/loader`.\n"})

            self.assertEqual(rows_of(report, "path-not-found"), [])
            self.assertEqual(self.scan.path_candidate("lib/drift-detector"),
                             "lib/drift-detector")

    # A call is not a location. The argument list disqualifies the token outright, and the same
    # expression with the arguments left off is a member selected out of a module, which makes the
    # module the reference.
    def test_a_member_access_is_not_a_missing_path(self):
        self.assertIsNone(self.scan.path_candidate("lib/pillars.init(projectRoot)"))

        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "lib/pillars.js": "export const init = () => 1\n",
                "README.md": "Call `lib/pillars.init(projectRoot)` or `lib/pillars.init`.\n"})

            self.assertEqual(rows_of(report, "path-not-found"), [])

    # A changelog names a path in order to say it is gone. That is a correct statement about the
    # repository, not a claim that drifted from it. The construction has to be there in full: a
    # verb of relocation, the token, a relation, and a successor on the far side of it.
    def test_a_renaming_line_does_not_report_the_old_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "lib/new-name.js": "export const a = 1\n",
                "CHANGELOG.md": "## 1.1.0\n\n"
                                "- Renamed `lib/old-name.js` -> `lib/new-name.js`.\n"
                                "- The loader `lib/loader.js` moved.\n"})
            rows = rows_of(report, "path-not-found")

            self.assertNotIn("lib/old-name.js", [row["claim"] for row in rows])
            self.assertEqual([row["claim"] for row in rows], ["lib/loader.js"])

    # A trailing slash is the writer saying the reference is a directory. Without one a bare word
    # with no extension is just a word, and with one the directory has to be there.
    def test_a_reference_to_a_real_directory_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(tmp, "monorepo")
            report = self.scan.scan(str(root), set(), False, 5)
            ctx = index_ctx(self.scan, root)

            self.assertEqual(rows_of(report, "path-not-found"), [])
            self.assertEqual(self.scan.resolve_path(ctx, "", "apps/web"), "apps/web")
            self.assertEqual(self.scan.resolve_path(ctx, "", "packages/shared"),
                             "packages/shared")
            self.assertEqual(self.scan.path_candidate("packages/shared/"), "packages/shared")
            self.assertEqual(self.scan.path_candidate("config/"), "config")
            self.assertIsNone(self.scan.path_candidate("config"))


class DeniedPresenceTests(unittest.TestCase):
    def setUp(self):
        self.scan = load_scan()

    def scan_tree(self, tmp, files):
        for rel, body in files.items():
            write(tmp, rel, body)
        return self.scan.scan(str(tmp), set(), False, 5)

    # A deletion report names the file it deleted. The predicate comes first and the token is its
    # object, which is the direction the old line-and-tail test could not see at all. The finding
    # on the next bullet is the control: nothing about the report suppresses a live reference.
    def test_a_deletion_verb_in_front_of_the_token_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "apps/web/src/lib/keep.ts": "export const keep = 1\n",
                "docs/reports/removal.md":
                    "# Demo State Removal\n\n"
                    "## Removed Active State\n\n"
                    "- Deleted the orphan `apps/web/src/lib/demoData.ts` module.\n"
                    "- The replacement lives in `apps/web/src/lib/realData.ts`.\n"})
            rows = rows_of(report, "path-not-found")

            self.assertEqual([row["claim"] for row in rows],
                             ["apps/web/src/lib/realData.ts"])
            self.assertEqual(rows[0]["confidence"], "low")
            self.assertEqual(rows[0]["precision_note"], self.scan.PATH_PRECISION_NOTE)

    # The same denial pointed forwards, and wrapped: the token ends one line and the predicate that
    # denies it starts the next. The sentence is the unit that carries the claim, so the scope has
    # to be the sentence and not the line.
    def test_a_wrapped_sentence_denying_the_token_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "schema/agent.json": "{}\n",
                "ARCHITECTURE.md":
                    "## Target shape\n\n"
                    "> STATUS: ASPIRATIONAL / NOT YET IMPLEMENTED. The agents shipped today use\n"
                    "> flat frontmatter; none carry the contract block below, and\n"
                    "> `schema/agent-manifest.v1.json` does\n"
                    "> not exist yet. Treat this as design intent.\n\n"
                    "The loader is `schema/agent-loader.json`.\n"})
            rows = rows_of(report, "path-not-found")

            self.assertEqual([row["claim"] for row in rows], ["schema/agent-loader.json"])

    # The verb has to reach the token. "deleted-items" is a name, not a predicate, and "lives in"
    # is a second predicate that takes the token away from the first, so both of these are live
    # references that should still be reported.
    def test_a_removal_word_that_does_not_govern_the_token_stays_reportable(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.scan_tree(tmp, {
                "docs/index.md": "# docs\n",
                "README.md":
                    "The deleted-items log lives in `docs/deletions.md`.\n\n"
                    "The removed helper is `docs/legacy.md`.\n"})

            self.assertEqual(claims(report, "path-not-found"),
                             ["docs/deletions.md", "docs/legacy.md"])
            self.assertFalse(self.scan.governed_removal("The deleted-items log lives in `"))
            self.assertTrue(self.scan.governed_removal("- Deleted the orphan `"))

    # A report that swallowed nine hundred findings and a report that swallowed three both said
    # "truncated". The gates are counted for the same reason: a reader who cannot see how much was
    # dropped cannot tell a filtered view from a complete one.
    def test_the_report_records_what_the_gates_and_the_cap_discarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            links = "".join("- [%d](docs/missing-%d.md)\n" % (number, number)
                            for number in range(250))
            report = self.scan_tree(tmp, {
                "docs/index.md": "# docs\n",
                "src/app.js": "console.log(1)\n",
                "README.md": "Read `notes.md`, then `bundled/app.js`, then `nowhere/thing.md`.\n\n"
                             + links})
            stats = report["scan"]["drift"]

            self.assertEqual(stats["found"], 250)
            self.assertEqual(stats["emitted"], self.scan.MAX_DRIFT)
            self.assertEqual(len(report["drift"]), self.scan.MAX_DRIFT)
            self.assertTrue(stats["truncated"])
            self.assertTrue(report["scan"]["truncated"])
            self.assertEqual(stats["discarded"]["bare_name_outside_a_link"], 1)
            self.assertEqual(stats["discarded"]["basename_found_elsewhere"], 1)
            self.assertEqual(stats["discarded"]["first_component_not_a_directory"], 1)
            self.assertEqual(stats["candidates"], 253)


if __name__ == "__main__":
    unittest.main()
