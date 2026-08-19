import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROSE = ROOT / "skill" / "scripts" / "docdna_prose.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "prose"


def load_prose():
    spec = importlib.util.spec_from_file_location("docdna_prose_test", PROSE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Implements: P-MUST-01
class ProseReviewTests(unittest.TestCase):
    def setUp(self):
        self.prose = load_prose()

    def test_reports_each_supported_pattern_with_a_location(self):
        text = """# Three Structural Problems to Solve

Experts believe this groundbreaking tool serves as more than a checker.
In order to continue, use it not just for lint, but also for review.
Of course, the future looks bright.
"""

        findings = self.prose.inspect_text(text)

        self.assertEqual({row["kind"] for row in findings},
                         {"title-case-heading", "vague-attribution",
                          "promotional-language", "fancy-copula", "filler-phrase",
                          "stock-contrast", "chatbot-phrase", "generic-conclusion"})
        vague = next(row for row in findings if row["kind"] == "vague-attribution")
        self.assertEqual((vague["line"], vague["column"]), (3, 1))

    def test_ignores_frontmatter_literal_regions_comments_and_link_destinations(self):
        text = """---
title: Experts Believe
---

`Experts believe` is an example.

```text
Of course, this is groundbreaking.
```

<!--
In order to hide an editorial note.
-->

[plain link](https://example.com/experts-believe)

`<!--` <!-- hidden --> Analysts warn about a risk.

Researchers suggest a change.
"""

        findings = self.prose.inspect_text(text)

        self.assertEqual([(row["kind"], row["line"]) for row in findings],
                         [("vague-attribution", 17), ("vague-attribution", 19)])

    def test_sentence_case_headings_and_mixed_case_names_are_not_title_case_findings(self):
        text = """# How DocDNA checks prose

## What the checker cannot decide
"""

        self.assertEqual(self.prose.inspect_text(text), [])

    def test_P_MUST_01_protected_spans_emit_no_prose_findings(self):
        text = (FIXTURES / "protected-spans.md").read_text(encoding="utf-8")

        self.assertEqual(self.prose.inspect_text(text, path="docs/protected-spans.md"), [])

    def test_visible_prose_beside_each_protected_span_is_still_reported(self):
        text = (FIXTURES / "visible-findings.md").read_text(encoding="utf-8")

        findings = self.prose.inspect_text(text, path="docs/visible-findings.md")

        self.assertEqual(
            [(row["kind"], row["line"], row["column"]) for row in findings],
            [
                ("vague-attribution", 3, 25),
                ("filler-phrase", 4, 25),
                ("vague-attribution", 5, 48),
                ("promotional-language", 6, 44),
                ("chatbot-phrase", 7, 21),
                ("vague-attribution", 8, 30),
                ("vague-attribution", 9, 37),
                ("vague-attribution", 10, 25),
                ("vague-attribution", 12, 1),
                ("generic-conclusion", 17, 22),
            ],
        )

    def test_commonmark_autolinks_and_reference_destinations_are_protected(self):
        text = (FIXTURES / "protected-spans.md").read_text(encoding="utf-8")

        inventory = self.prose.protected_inventory(text)

        self.assertEqual(
            set(inventory["link_targets"]),
            {
                "https://example.test/(Experts-believe)/groundbreaking",
                "https://example.test/it-is-important-to-note-that",
                "groundbreaking@example.com",
                "ftp://example.test/groundbreaking",
                "custom:groundbreaking",
                "/groundbreaking",
            },
        )

    def test_nested_parentheses_and_escaped_delimiters_preserve_source_columns(self):
        text = ("[source](https://example.test/a_(b\\)c)) Experts believe this.\n"
                "`literal `` delimiter` Analysts warn about latency.\n")

        findings = self.prose.inspect_text(text, path="docs/guide.md")

        self.assertEqual(
            [(row["kind"], row["line"], row["column"]) for row in findings],
            [("vague-attribution", 1, 41), ("vague-attribution", 2, 24)],
        )

    def test_inline_link_scan_is_linear_and_requires_a_link_opener(self):
        class CountingLine(str):
            def __new__(cls, value):
                instance = str.__new__(cls, value)
                instance.work = 0
                return instance

            def __getitem__(self, key):
                self.work += 1
                return str.__getitem__(self, key)

            def find(self, substring, start=0, *args):
                self.work += max(0, len(self) - start)
                return str.find(self, substring, start, *args)

        adversarial = CountingLine("](" * 4000)

        self.assertEqual(self.prose._link_ranges(adversarial,
                                                [False] * len(adversarial)), [])
        self.assertLessEqual(adversarial.work, len(adversarial) * 8)

        escaped = CountingLine("[docs](" + "\\" * 4000 + "target)")
        self.assertEqual(
            self.prose._link_ranges(escaped, [False] * len(escaped)),
            [(7, len(escaped) - 1)],
        )
        self.assertLessEqual(escaped.work, len(escaped) * 8)

        titled = CountingLine("[docs](/target \"" + "\\" * 4000 + "title\")")
        self.assertEqual(
            self.prose._link_ranges(titled, [False] * len(titled)),
            [(7, 14)],
        )
        self.assertLessEqual(titled.work, len(titled) * 8)

        reference = CountingLine("[docs]: " + "\\" * 4000 + "target")
        self.assertEqual(
            self.prose._reference_target(reference, [False] * len(reference)),
            (8, len(reference), reference[8:]),
        )
        self.assertLessEqual(reference.work, len(reference) * 8)

        text = ("Experts believe ](/groundbreaking) remains literal.\n"
                "[docs](/groundbreaking) Researchers suggest a change.\n")
        findings = self.prose.inspect_text(text)
        self.assertEqual(
            [(row["kind"], row["line"], row["column"]) for row in findings],
            [("vague-attribution", 1, 1), ("promotional-language", 1, 20),
             ("vague-attribution", 2, 25)],
        )

    def test_protected_or_invalid_brackets_cannot_open_an_inline_link(self):
        cases = (
            '"literal [" ](/groundbreaking) remains visible.\n',
            '<!-- [ --> ](/groundbreaking) remains visible.\n',
            '`[` ](/groundbreaking) remains visible.\n',
            '<custom:[> ](/groundbreaking) remains visible.\n',
            '[valid](custom:[token]) ](/groundbreaking) remains visible.\n',
        )
        for text in cases:
            with self.subTest(text=text):
                findings = self.prose.inspect_text(text)
                self.assertEqual(
                    [(row["kind"], row["match"]) for row in findings],
                    [("promotional-language", "groundbreaking")],
                )

    def test_multiline_inline_code_preserves_only_neighboring_visible_prose(self):
        text = ("Before ``Experts believe\n"
                "this is groundbreaking`` Researchers suggest a change.\n")

        findings = self.prose.inspect_text(text)
        inventory = self.prose.protected_inventory(text)

        self.assertEqual(
            [(row["kind"], row["line"], row["column"]) for row in findings],
            [("vague-attribution", 2, 26)],
        )
        self.assertEqual(inventory["inline_code"],
                         ["``Experts believe\nthis is groundbreaking``"])

    def test_multiline_inline_code_stops_at_markdown_block_boundaries(self):
        cases = (
            ("# Heading `Experts believe\n"
             "Paragraph closes` Researchers suggest a change.\n",
             [("vague-attribution", 1, 12), ("vague-attribution", 2, 19)]),
            ("> `Experts believe\n"
             "groundbreaking` Researchers suggest a change.\n",
             [("vague-attribution", 1, 4), ("promotional-language", 2, 1),
              ("vague-attribution", 2, 17)]),
            ("- `Experts believe in item one\n"
             "- item two closes` Researchers suggest a change.\n",
             [("vague-attribution", 1, 4), ("vague-attribution", 2, 20)]),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                findings = self.prose.inspect_text(text)
                self.assertEqual(
                    [(row["kind"], row["line"], row["column"]) for row in findings],
                    expected,
                )
                self.assertEqual(self.prose.protected_inventory(text)["inline_code"], [])

    def test_fenced_blocks_nested_in_block_quotes_are_protected_and_inventoried(self):
        text = ("> ```text\n"
                "> Experts believe this is groundbreaking.\n"
                "> ```\n"
                "> Researchers suggest the visible change.\n")

        findings = self.prose.inspect_text(text)
        inventory = self.prose.protected_inventory(text)

        self.assertEqual(
            [(row["kind"], row["line"], row["column"]) for row in findings],
            [("vague-attribution", 4, 3)],
        )
        self.assertEqual(
            inventory["fenced_blocks"],
            ["> ```text\n> Experts believe this is groundbreaking.\n> ```"],
        )

    def test_unclosed_comment_and_fence_protect_only_their_actual_remainder(self):
        comment = "Experts believe this. <!-- In order to continue\nAnalysts warn here.\n"
        fence = "Researchers suggest this.\n```text\nOf course, this is groundbreaking.\n"

        self.assertEqual(
            [(row["kind"], row["line"]) for row in self.prose.inspect_text(comment)],
            [("vague-attribution", 1)],
        )
        self.assertEqual(
            [(row["kind"], row["line"]) for row in self.prose.inspect_text(fence)],
            [("vague-attribution", 1)],
        )

    def test_humanizer_true_positive_and_restraint_cases(self):
        corpus = json.loads((FIXTURES / "humanizer-cases.json").read_text(encoding="utf-8"))

        for case in corpus["cases"]:
            with self.subTest(case=case["id"]):
                findings = self.prose.inspect_text(case["text"], path=case["path"])
                self.assertEqual(
                    Counter(row["kind"] for row in findings),
                    Counter(case["expected_kinds"]),
                )

    def test_context_sensitive_patterns_require_recurrence_or_allowed_path_context(self):
        lone_transition = "Moreover, the cache owns this record.\n"
        lone_lexical = "The parser accepts an intricate data structure.\n"
        passive = "The record is written by the worker.\n"
        diff_sentence = "A registry check was added to the command.\n"
        distant_transitions = ("Moreover, the cache owns this record.\n\n"
                               "The worker removes expired records.\n\n"
                               "Furthermore, the command reports a count.\n")
        distant_lexical = ("The parser accepts an intricate structure.\n\n"
                           "The command prints its result.\n\n"
                           "The pivotal decision belongs to the operator.\n")

        self.assertEqual(self.prose.inspect_text(lone_transition, path="docs/guide.md"), [])
        self.assertEqual(self.prose.inspect_text(lone_lexical, path="docs/guide.md"), [])
        self.assertEqual(self.prose.inspect_text(passive, path="docs/guide.md"), [])
        self.assertEqual(self.prose.inspect_text(distant_transitions, path="docs/guide.md"), [])
        self.assertEqual(self.prose.inspect_text(distant_lexical, path="docs/guide.md"), [])
        for path in ("CHANGELOG.md", "RELEASE_NOTES.md", "MIGRATIONS.md",
                     "docs/release-notes/1.4.md", "docs/migrations/registry.md",
                     "db/migration_001.md"):
            with self.subTest(path=path):
                self.assertEqual(self.prose.inspect_text(diff_sentence, path=path), [])

    def test_prose_comparison_preserves_protected_inventory(self):
        before = (FIXTURES / "prose-before.md").read_text(encoding="utf-8")
        safe = (FIXTURES / "prose-after-safe.md").read_text(encoding="utf-8")
        unsafe = (FIXTURES / "prose-after-unsafe.md").read_text(encoding="utf-8")

        safe_result = self.prose.compare_texts(before, safe)
        unsafe_result = self.prose.compare_texts(before, unsafe)

        self.assertTrue(safe_result["protected_inventory_unchanged"])
        self.assertEqual(safe_result["added"], {})
        self.assertEqual(safe_result["removed"], {})
        self.assertFalse(unsafe_result["protected_inventory_unchanged"])
        self.assertEqual(safe_result["before"]["table_shape"], ["columns:2"] * 5)
        self.assertEqual(safe_result["after"]["table_shape"], ["columns:2"] * 5)
        for category in ("frontmatter", "citations", "gap_markers", "numbers",
                         "inline_code", "link_targets", "fenced_blocks",
                         "path_tokens", "table_shape"):
            self.assertIn(category, set(unsafe_result["added"]) | set(unsafe_result["removed"]))
        self.assertIn("revision: 4", unsafe_result["added"]["frontmatter"])
        self.assertIn("revision: 3", unsafe_result["removed"]["frontmatter"])
        self.assertIn("30", unsafe_result["added"]["numbers"])
        self.assertIn("20", unsafe_result["removed"]["numbers"])
        self.assertIn("[ref: deployment handbook, verified 2026-08-19]",
                      unsafe_result["added"]["citations"])
        self.assertIn("[ref: operator handbook, verified 2026-08-19]",
                      unsafe_result["removed"]["citations"])
        self.assertIn("https://docs.example.test/verification",
                      unsafe_result["added"]["link_targets"])
        self.assertIn("https://docs.example.test/runtime",
                      unsafe_result["removed"]["link_targets"])
        self.assertIn("/docs/verification", unsafe_result["added"]["link_targets"])
        self.assertIn("/docs/runtime", unsafe_result["removed"]["link_targets"])
        self.assertIn("ftp://docs.example.test/verification",
                      unsafe_result["added"]["link_targets"])
        self.assertIn("ftp://docs.example.test/runtime",
                      unsafe_result["removed"]["link_targets"])

    def test_prose_comparison_reports_soft_inference_review(self):
        before = (FIXTURES / "prose-before.md").read_text(encoding="utf-8")
        after = (FIXTURES / "prose-after-safe.md").read_text(encoding="utf-8")

        result = self.prose.compare_texts(before, after)

        review = result["soft_inference_review"]
        self.assertEqual(review["status"], "unverified")
        self.assertEqual({question["kind"] for question in review["questions"]},
                         {"causal", "temporal", "quantitative"})
        self.assertTrue(all(question["requires_meaning_review"]
                            for question in review["questions"]))

        process = subprocess.run(
            [sys.executable, str(PROSE), "--compare", str(FIXTURES / "prose-before.md"),
             str(FIXTURES / "prose-after-safe.md"), "--json"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(process.stdout)
        self.assertEqual(payload["soft_inference_review"], review)

        unsafe = subprocess.run(
            [sys.executable, str(PROSE), "--compare", str(FIXTURES / "prose-before.md"),
             str(FIXTURES / "prose-after-unsafe.md"), "--json"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(unsafe.returncode, 1, unsafe.stderr)

    def test_compare_cli_reports_missing_or_unreadable_inputs_without_traceback(self):
        before = FIXTURES / "prose-before.md"
        missing = FIXTURES / "missing-prose-input.md"

        cases = (
            ([str(missing), str(before)],
             "docdna_prose: cannot read BEFORE input: %s\n" % missing),
            ([str(before), str(FIXTURES)],
             "docdna_prose: cannot read AFTER input: %s\n" % FIXTURES),
        )
        for paths, expected_stderr in cases:
            with self.subTest(paths=paths):
                process = subprocess.run(
                    [sys.executable, str(PROSE), "--compare"] + paths + ["--json"],
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(process.returncode, 2)
                self.assertEqual(process.stdout, "")
                self.assertEqual(process.stderr, expected_stderr)
                self.assertNotIn("Traceback", process.stderr)

    def test_compare_cli_rejects_oversized_symlinked_and_fifo_inputs(self):
        before = FIXTURES / "prose-before.md"
        max_bytes = self.prose.MAX_PROSE_BYTES
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            oversized = temporary / "oversized.md"
            with oversized.open("wb") as handle:
                handle.truncate(max_bytes + 1)
            symlink = temporary / "linked.md"
            symlink.symlink_to(before)
            cases = [oversized, symlink]
            if hasattr(os, "mkfifo"):
                fifo = temporary / "stream.md"
                os.mkfifo(str(fifo))
                cases.append(fifo)

            for candidate in cases:
                with self.subTest(candidate=candidate):
                    process = subprocess.run(
                        [sys.executable, str(PROSE), "--compare", str(before),
                         str(candidate), "--json"],
                        text=True,
                        capture_output=True,
                        timeout=2,
                    )
                    self.assertEqual(process.returncode, 2)
                    self.assertEqual(process.stdout, "")
                    self.assertEqual(
                        process.stderr,
                        "docdna_prose: cannot read AFTER input: %s\n" % candidate,
                    )
                    self.assertNotIn("Traceback", process.stderr)


if __name__ == "__main__":
    unittest.main()
