import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNICODE = ROOT / "skill" / "scripts" / "docdna_unicode.py"


def load_unicode():
    spec = importlib.util.spec_from_file_location("docdna_unicode_test", UNICODE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UnicodeHygieneTests(unittest.TestCase):
    def setUp(self):
        self.hygiene = load_unicode()

    def test_inspect_reports_exact_codepoint_position_and_severity(self):
        findings = self.hygiene.inspect_text("safe\nleft\u202eright\n")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["codepoint"], "U+202E")
        self.assertEqual(findings[0]["name"], "RIGHT-TO-LEFT OVERRIDE")
        self.assertEqual(findings[0]["kind"], "bidi")
        self.assertEqual(findings[0]["severity"], "major")
        self.assertEqual(findings[0]["line"], 2)
        self.assertEqual(findings[0]["column"], 5)

    def test_tag_characters_are_major_findings(self):
        findings = self.hygiene.inspect_text("visible\U000E0061text")

        self.assertEqual([(row["codepoint"], row["kind"], row["severity"])
                          for row in findings], [("U+E0061", "tag", "major")])

    def test_terminal_controls_are_major_but_text_whitespace_is_allowed(self):
        findings = self.hygiene.inspect_text("tab\tline\nreturn\r escape\x1b end\x7f")

        self.assertEqual([(row["codepoint"], row["kind"], row["severity"])
                          for row in findings],
                         [("U+001B", "control", "major"),
                          ("U+007F", "control", "major")])

    def test_surrogates_and_noncharacters_are_removed_before_utf8_output(self):
        text = "safe\ud800text\ufdd0end\U0010ffff"

        findings = self.hygiene.inspect_text(text)
        cleaned, stats = self.hygiene.clean_generated_text(text)

        self.assertEqual([row["codepoint"] for row in findings],
                         ["U+D800", "U+FDD0", "U+10FFFF"])
        self.assertTrue(all(row["kind"] == "control" for row in findings))
        self.assertEqual(cleaned, "safetextend")
        self.assertEqual(stats["removed_count"], 3)
        cleaned.encode("utf-8")

    def test_invisible_format_and_exotic_spaces_are_minor_findings(self):
        findings = self.hygiene.inspect_text("a\u200bb\u00a0c")

        self.assertEqual([(row["codepoint"], row["kind"], row["severity"])
                          for row in findings],
                         [("U+200B", "zero-width", "minor"),
                          ("U+00A0", "space", "minor")])

    def test_cleaner_strips_controls_and_normalizes_space_lookalikes(self):
        cleaned, stats = self.hygiene.clean_generated_text("a\u200bb\u202fc\u202ed")

        self.assertEqual(cleaned, "ab cd")
        self.assertEqual(stats["removed_count"], 2)
        self.assertEqual(stats["replaced_count"], 1)
        self.assertEqual(stats["by_kind"], {"bidi": 1, "space": 1, "zero-width": 1})

    def test_legitimate_emoji_presentation_glue_is_preserved(self):
        heart_on_fire = "\u2764\ufe0f\u200d\U0001f525"
        family = "\U0001f468\u200d\U0001f469\u200d\U0001f467"

        for text in (heart_on_fire, family):
            with self.subTest(text=text):
                self.assertEqual(self.hygiene.inspect_text(text), [])
                self.assertEqual(self.hygiene.clean_generated_text(text)[0], text)

    def test_free_floating_emoji_glue_is_still_reported_and_removed(self):
        text = "plain\u200dtext\ufe0f"

        findings = self.hygiene.inspect_text(text)
        cleaned, stats = self.hygiene.clean_generated_text(text)

        self.assertEqual([row["codepoint"] for row in findings], ["U+200D", "U+FE0F"])
        self.assertEqual(cleaned, "plaintext")
        self.assertEqual(stats["removed_count"], 2)

    def test_plain_unicode_text_is_left_byte_identical(self):
        text = "Configuration for caf\u00e9 and \u6771\u4eac.\n"

        self.assertEqual(self.hygiene.inspect_text(text), [])
        self.assertEqual(self.hygiene.clean_generated_text(text),
                         (text, {"removed_count": 0, "replaced_count": 0, "by_kind": {}}))


if __name__ == "__main__":
    unittest.main()
