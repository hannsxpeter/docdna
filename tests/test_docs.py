import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill" / "SKILL.md"
SCRIPTS = ROOT / "skill" / "scripts"
WORKFLOWS = ROOT / ".github" / "workflows"
INSTALLER = ROOT / "install.sh"

MAX_DESCRIPTION = 1536
MAX_SKILL_LINES = 300

SKIP_DIRS = {".git", "design", "__pycache__", ".pytest_cache", "node_modules"}
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^\s*(?:```|~~~)")
SCRIPT_NAME = re.compile(r"docdna_[a-z_]+\.py")
SCRIPT_PATH = re.compile(r"skill/scripts/[A-Za-z0-9_.\-]+")
SOURCE_PATH = re.compile(r"\$SRC_DIR/([A-Za-z0-9_./\-]+)")
SKIP_LINK = ("http://", "https://", "mailto:", "tel:", "#", "<")

EM_DASH = "\u2014"
EN_DASH = "\u2013"
EMOJI_RANGES = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0xFE00, 0xFE0F))


def text_of(path):
    raw = path.read_bytes()
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def repo_files():
    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if set(path.relative_to(ROOT).parts[:-1]) & SKIP_DIRS:
            continue
        files.append(path)
    return files


def documented_files():
    files = [ROOT / "README.md", SKILL, ROOT / "CONTRIBUTING.md"]
    files.extend(sorted((ROOT / "docs").rglob("*.md")))
    return [path for path in files if path.is_file()]


def frontmatter(path):
    lines = (text_of(path) or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    data = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return data
        if line[:1] in (" ", "\t") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return None


def links(text):
    found = []
    fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fence = not fence
            continue
        if fence:
            continue
        for target in LINK.findall(line):
            found.append((number, target))
    return found


def relative_link(target):
    if target.startswith(SKIP_LINK) or "://" in target:
        return None
    clean = target.split("#", 1)[0].split("?", 1)[0]
    return clean or None


def is_emoji(point):
    for low, high in EMOJI_RANGES:
        if low <= point <= high:
            return True
    return False


def offenders(text):
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for char in line:
            if char in (EM_DASH, EN_DASH) or is_emoji(ord(char)):
                found.append("line %d: U+%04X" % (number, ord(char)))
    return found


class SkillDocumentTests(unittest.TestCase):
    def test_skill_frontmatter_carries_a_name_and_a_description(self):
        data = frontmatter(SKILL)

        self.assertIsNotNone(data, "skill/SKILL.md has no terminated frontmatter block")
        self.assertEqual(data.get("name"), "docdna")
        self.assertTrue(data.get("description"))
        self.assertIn("allowed-tools", data)

    def test_skill_description_stays_under_the_limit(self):
        description = frontmatter(SKILL)["description"]

        self.assertLess(len(description), MAX_DESCRIPTION,
                        "description is %d characters" % len(description))

    def test_skill_md_stays_under_three_hundred_lines(self):
        count = len(SKILL.read_text(encoding="utf-8").splitlines())

        self.assertLess(count, MAX_SKILL_LINES, "skill/SKILL.md is %d lines" % count)


class LinkTests(unittest.TestCase):
    def test_relative_markdown_links_resolve(self):
        checked = 0
        broken = []
        for path in documented_files():
            for number, target in links(text_of(path) or ""):
                clean = relative_link(target)
                if clean is None:
                    continue
                checked += 1
                if not (path.parent / clean).resolve().exists():
                    broken.append("%s:%d -> %s" % (path.relative_to(ROOT), number, target))

        self.assertGreater(checked, 0, "no relative markdown links were found to check")
        self.assertEqual(broken, [])


class HouseStyleTests(unittest.TestCase):
    def test_no_file_carries_an_em_dash_an_en_dash_or_an_emoji(self):
        checked = 0
        found = {}
        for path in repo_files():
            text = text_of(path)
            if text is None:
                continue
            checked += 1
            hits = offenders(text)
            if hits:
                found[str(path.relative_to(ROOT))] = hits[:5]

        self.assertGreater(checked, 20, "the walk found almost nothing to check")
        self.assertEqual(found, {})

    def test_the_walk_would_catch_an_offending_character(self):
        self.assertEqual(offenders("a " + EM_DASH + " b"), ["line 1: U+2014"])
        self.assertEqual(offenders("pages 10" + EN_DASH + "15"), ["line 1: U+2013"])
        self.assertEqual(offenders("ship it \U0001F680"), ["line 1: U+1F680"])
        self.assertEqual(offenders("done \u2705"), ["line 1: U+2705"])
        self.assertEqual(offenders("pages 10-15, a - b, ok"), [])


class ReferenceTests(unittest.TestCase):
    def script_names(self):
        return set(path.name for path in SCRIPTS.glob("docdna_*.py"))

    def test_installer_references_only_files_that_exist(self):
        text = INSTALLER.read_text(encoding="utf-8")
        sources = SOURCE_PATH.findall(text)

        self.assertGreater(len(sources), 0, "the installer names no source paths")
        for rel in sources:
            self.assertTrue((ROOT / rel).exists(), "install.sh names missing %s" % rel)
        for name in set(SCRIPT_NAME.findall(text)):
            self.assertIn(name, self.script_names())

    def test_ci_workflow_references_only_scripts_that_exist(self):
        workflows = sorted(WORKFLOWS.glob("*.yml"))
        referenced = set()

        self.assertGreater(len(workflows), 0, "no workflow files were found")
        for path in workflows:
            text = path.read_text(encoding="utf-8")
            for rel in set(SCRIPT_PATH.findall(text)):
                self.assertTrue((ROOT / rel).is_file(),
                                "%s names missing %s" % (path.name, rel))
                referenced.add(Path(rel).name)
            for name in set(SCRIPT_NAME.findall(text)):
                self.assertIn(name, self.script_names(),
                              "%s names missing %s" % (path.name, name))
        self.assertGreater(len(referenced), 0, "no workflow runs any helper script")

    def test_the_installer_is_executable(self):
        self.assertTrue(INSTALLER.exists(), "install.sh is missing")

        mode = INSTALLER.stat().st_mode
        self.assertTrue(mode & 0o111,
                        "install.sh is mode %o; README documents ./install.sh, which needs +x"
                        % (mode & 0o777))

    def test_ci_workflow_compiles_every_helper(self):
        compiled = set()
        for path in sorted(WORKFLOWS.glob("*.yml")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if "py_compile" not in line:
                    continue
                compiled.update(Path(rel).name for rel in SCRIPT_PATH.findall(line))

        self.assertEqual(compiled, self.script_names())


if __name__ == "__main__":
    unittest.main()
