"""Pin the facts the prose quotes about the catalog to the catalog itself.

Two reference files carried counts from the first 60-entry catalog for three releases after it grew to
96, because nothing compared them. Every count below is read from the shipped JSON, so a catalog change
that moves one fails here until the prose that quotes it is corrected in the same commit.
"""

import collections
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "skill" / "catalog"
LIFECYCLE = ROOT / "skill" / "references" / "lifecycle.md"
SELECTION = ROOT / "skill" / "references" / "selection.md"
SCHEMA_DOC = CATALOG_DIR / "SCHEMA.md"

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
         9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
         15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
         20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty", 70: "seventy",
         80: "eighty", 90: "ninety"}
LAYER_BY_PRECEDENCE = {"0": "baseline", "10": "signal", "20": "overlay", "30": "answer",
                       "40": "override"}
TABLE_ROW = re.compile(r"^\|\s*`?([^|`]+?)`?\s*\|.*\|\s*(\d+)\s*\|\s*$")
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^\s*(?:```|~~~)")
CODE_SPAN = re.compile(r"`[^`]*`")
SKIP_LINK = ("http://", "https://", "mailto:", "tel:", "#", "<")
RETIRED_MARKER = "P-" + "MUST"


def word(number):
    if number in WORDS:
        return WORDS[number]
    tens, ones = divmod(number, 10)
    return "%s-%s" % (WORDS[tens * 10], WORDS[ones])


def load(name):
    with open(str(CATALOG_DIR / ("%s.json" % name)), encoding="utf-8") as handle:
        return json.load(handle)


def table_counts(path):
    counts = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = TABLE_ROW.match(line)
        if match:
            counts[match.group(1).strip()] = int(match.group(2))
    return counts


def markdown_files():
    files = [ROOT / name for name in ("README.md", "CONTRIBUTING.md", "CHANGELOG.md")]
    for folder in ("docs", "skill", "proof"):
        files.extend(sorted((ROOT / folder).rglob("*.md")))
    return [path for path in files if path.is_file()]


class CatalogCountsInProse(unittest.TestCase):
    def setUp(self):
        self.documents = load("documents")["documents"]

    def test_lifecycle_durability_table_matches_the_catalog(self):
        counts = collections.Counter(doc["durability"] for doc in self.documents)
        table = table_counts(LIFECYCLE)
        for durability, total in counts.items():
            self.assertEqual(table.get(durability), total, durability)

    def test_lifecycle_stage_table_matches_the_catalog(self):
        counts = collections.Counter(doc["stage"] for doc in self.documents)
        table = table_counts(LIFECYCLE)
        for stage, total in counts.items():
            self.assertEqual(table.get(stage), total, stage)

    def test_lifecycle_audience_and_cadence_sentences_match_the_catalog(self):
        text = " ".join(LIFECYCLE.read_text(encoding="utf-8").split())
        audiences = {name for doc in self.documents for name in doc["audiences"]}
        self.assertIn("across %s values" % word(len(audiences)), text)
        cadence = collections.Counter(str(doc["cadence"]) for doc in self.documents)
        self.assertIn("%s shipped entries use `on-change`, %s use `on-release`, and %s use `none`"
                      % (word(cadence["on-change"]).capitalize(), word(cadence["on-release"]),
                         word(cadence["none"])), text)

    def test_selection_rule_layer_table_matches_the_catalog(self):
        counts = collections.Counter(rule["layer"] for rule in load("rules")["rules"])
        rows = {}
        for line in SELECTION.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\|[^|]+\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*$", line)
            if match and match.group(1) in LAYER_BY_PRECEDENCE:
                rows[LAYER_BY_PRECEDENCE[match.group(1)]] = int(match.group(2))
        self.assertEqual(rows, dict(counts))

    def test_refusal_and_catalog_totals_match_the_catalog(self):
        refused = sum(1 for doc in self.documents if doc["producible"] == "R")
        phrase = "%s of the %s" % (word(refused).capitalize(), word(len(self.documents)))
        for path in (ROOT / "README.md", ROOT / "docs" / "COMPLIANCE.md"):
            text = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn(phrase, text, path.name)

    def test_schema_doc_lists_every_catalog_file(self):
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        files = sorted(path.name for path in CATALOG_DIR.glob("*.json"))
        for name in files:
            self.assertIn("| `%s` |" % name, text)
        self.assertIn("All %s are JSON" % word(len(files)), text)


class RepositoryProseHygiene(unittest.TestCase):
    def test_relative_links_resolve_across_every_markdown_file(self):
        broken = []
        for path in markdown_files():
            fence = False
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if FENCE.match(line):
                    fence = not fence
                    continue
                if fence:
                    continue
                for target in LINK.findall(CODE_SPAN.sub("", line)):
                    if target.startswith(SKIP_LINK) or "://" in target:
                        continue
                    clean = target.split("#", 1)[0].split("?", 1)[0]
                    if clean and not (path.parent / clean).resolve().exists():
                        broken.append("%s:%d -> %s" % (path.relative_to(ROOT), number, target))
        self.assertEqual(broken, [])

    def test_the_product_name_is_written_in_lowercase(self):
        offenders = []
        for path in markdown_files():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "DocDNA" in line:
                    offenders.append("%s:%d" % (path.relative_to(ROOT), number))
        self.assertEqual(offenders, [])

    def test_no_file_cites_the_retired_requirement_markers(self):
        offenders = []
        for folder in ("skill", "tests", "docs", "proof", ".github"):
            for path in sorted((ROOT / folder).rglob("*")):
                if not path.is_file() or "fixtures" in path.parts or "__pycache__" in path.parts:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if RETIRED_MARKER in text:
                    offenders.append(str(path.relative_to(ROOT)))
        for name in ("README.md", "CONTRIBUTING.md", "install.sh"):
            if RETIRED_MARKER in (ROOT / name).read_text(encoding="utf-8"):
                offenders.append(name)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
