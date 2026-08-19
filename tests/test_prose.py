import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROSE = ROOT / "skill" / "scripts" / "docdna_prose.py"


def load_prose():
    spec = importlib.util.spec_from_file_location("docdna_prose_test", PROSE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


if __name__ == "__main__":
    unittest.main()
