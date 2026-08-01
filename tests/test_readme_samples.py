"""Regenerate every documented sample of tool output and compare it byte for byte.

Seven consecutive review rounds shipped a hand-edited block of tool output in README.md, the last
one a real stdout capture with two of its eight family rows deleted. Human reading is not the
control that catches this, so the control is mechanical.

A fenced block counts as tool output only when the line above it carries a marker naming exactly
how to regenerate it:

    <!-- docdna:sample cmd="python3 skill/scripts/docdna_scan.py TARGET" target="." -->

TARGET is substituted with a throwaway copy of the named repository, so a command that writes a
manifest never touches the tree under test. The block must then equal that command's stdout with
no normalisation, no subset matching, and no tolerance: the defect being prevented is a deleted
row, and a subset match is exactly what a deleted row looks like.

An optional section="<header>" narrows the comparison to one blank-line-delimited section of
stdout, for the blocks that quote a single section rather than a whole run. The section is taken
whole, from its header to the blank line that closes it, so a row cannot be dropped out of the
middle or off the end of one either.

A fence with no marker is prose and is skipped, which is the only way a reader-typed shell command
can sit in the same document. The one thing an unmarked fence may not do is carry a line that the
report renderers emit as a section header, because that is the fabricated sample this file exists
to forbid, wearing a disguise.
"""

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skill" / "scripts"
DOCUMENTS = ("README.md", "skill/SKILL.md")

MARKER = re.compile(r"^<!--\s*docdna:sample\s+(.+?)\s*-->$")
ATTRIBUTE = re.compile(r'([a-z_]+)="([^"]*)"')
FENCE = re.compile(r"^(\s*)(```|~~~)(.*)$")

TARGET_TOKEN = "TARGET"
INTERPRETER = "python3"
REQUIRED_KEYS = ("cmd", "target")
OPTIONAL_KEYS = ("section",)
MINIMUM_SAMPLES = 2

# Section headers the two renderers emit. An unmarked fence carrying one of these is a sample of
# tool output that has escaped the regeneration check, which is how the deleted rows got in.
REPORT_HEADERS = (
    "not looked at, or refused",
    "present signals",
    "drift, most specific first",
    "MISSING AND LOAD-BEARING",
    "NOT APPLICABLE",
    "POSSIBLE STALE REFERENCES",
    "ORPHANED",
    "UNCERTAIN",
)

OUTPUT_CACHE = {}


def read_document(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def parse_marker(line):
    match = MARKER.match(line.strip())
    if match is None:
        return None
    attributes = dict(ATTRIBUTE.findall(match.group(1)))
    return attributes or {}


def fenced_blocks(text):
    lines = text.split("\n")
    blocks = []
    index = 0
    while index < len(lines):
        opening = FENCE.match(lines[index])
        if opening is None:
            index += 1
            continue
        indent, ticks, info = opening.group(1), opening.group(2), opening.group(3)
        body = []
        cursor = index + 1
        closed = False
        while cursor < len(lines):
            closing = FENCE.match(lines[cursor])
            if closing is not None and closing.group(2) == ticks and not closing.group(3).strip():
                closed = True
                break
            body.append(lines[cursor][len(indent):] if lines[cursor][:len(indent)] == indent
                        else lines[cursor])
            cursor += 1
        marker = None
        previous = index - 1
        while previous >= 0 and not lines[previous].strip():
            previous -= 1
        if previous >= 0:
            marker = parse_marker(lines[previous])
        blocks.append({"line": index + 1, "info": info.strip(), "body": "\n".join(body),
                       "marker": marker, "closed": closed,
                       "marker_line": previous + 1 if marker is not None else None})
        index = cursor + 1
    return blocks


def marked_blocks(text, source):
    found = []
    for block in fenced_blocks(text):
        if block["marker"] is None:
            continue
        block["source"] = source
        found.append(block)
    return found


def all_marked_blocks():
    found = []
    for rel in DOCUMENTS:
        found.extend(marked_blocks(read_document(rel), rel))
    return found


def marker_problems(block):
    marker = block["marker"]
    where = "%s:%d" % (block["source"], block["marker_line"])
    problems = []
    if not block["closed"]:
        problems.append("%s: the marked fence is never closed" % where)
    for key in REQUIRED_KEYS:
        if not marker.get(key):
            problems.append('%s: the marker has no %s="..." attribute' % (where, key))
    unknown = sorted(set(marker) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        problems.append("%s: the marker carries unknown attributes %s" % (where, ", ".join(unknown)))
    if problems:
        return problems
    command = marker["cmd"]
    if command.split().count(TARGET_TOKEN) != 1:
        problems.append("%s: cmd must name %s exactly once" % (where, TARGET_TOKEN))
    argv = shlex.split(command)
    if not argv or argv[0] != INTERPRETER:
        problems.append("%s: cmd must start with %s" % (where, INTERPRETER))
    elif len(argv) < 2 or not (ROOT / argv[1]).is_file():
        problems.append("%s: cmd names no script that exists: %s" % (where, command))
    elif (ROOT / argv[1]).parent != SCRIPTS:
        problems.append("%s: cmd runs something outside skill/scripts: %s" % (where, argv[1]))
    target = (ROOT / marker["target"]).resolve()
    if not target.is_dir():
        problems.append("%s: target is not a directory in this repository: %s"
                        % (where, marker["target"]))
    elif ROOT not in target.parents and target != ROOT:
        problems.append("%s: target sits outside this repository: %s" % (where, marker["target"]))
    return problems


def runnable(marker):
    words = shlex.split(marker.get("cmd") or "")
    if len(words) < 2 or words[0] != INTERPRETER or not (ROOT / words[1]).is_file():
        return None, "the marker names no runnable command: %r" % marker.get("cmd")
    if words.count(TARGET_TOKEN) != 1:
        return None, "the marker names %s %d times" % (TARGET_TOKEN, words.count(TARGET_TOKEN))
    if not (ROOT / (marker.get("target") or "")).is_dir():
        return None, "the marker names no target directory: %r" % marker.get("target")
    return words, None


def run_sample(marker):
    words, problem = runnable(marker)
    if problem is not None:
        return None, "", problem
    key = (marker["cmd"], marker["target"])
    if key in OUTPUT_CACHE:
        return OUTPUT_CACHE[key]
    source = (ROOT / marker["target"]).resolve()
    workspace = tempfile.mkdtemp(prefix="docdna-sample-")
    try:
        copy = os.path.join(workspace, source.name or "repo")
        shutil.copytree(str(source), copy, symlinks=True)
        argv = [sys.executable, str(ROOT / words[1])]
        argv.extend(copy if word == TARGET_TOKEN else word for word in words[2:])
        process = subprocess.run(argv, cwd=str(ROOT), stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        stdout = process.stdout.decode("utf-8")
        stderr = process.stderr.decode("utf-8")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    OUTPUT_CACHE[key] = (process.returncode, stdout, stderr)
    return OUTPUT_CACHE[key]


def section_of(stdout, header):
    lines = stdout.split("\n")
    starts = [index for index, line in enumerate(lines) if line == header]
    if not starts:
        return None, "stdout has no section headed %r" % header
    if len(starts) > 1:
        return None, "stdout heads %d sections %r, so the sample is ambiguous" % (len(starts),
                                                                                  header)
    start = starts[0]
    if start and lines[start - 1].strip():
        return None, "%r is not the first line of a section" % header
    end = start
    while end < len(lines) and lines[end] != "":
        end += 1
    return "\n".join(lines[start:end]), None


def expected_output(marker):
    code, stdout, stderr = run_sample(marker)
    if code is None:
        return None, stderr
    if code != 0:
        return None, "the command exited %d: %s" % (code, stderr.strip() or "no stderr")
    body = stdout[:-1] if stdout.endswith("\n") else stdout
    if not marker.get("section"):
        return body, None
    return section_of(body, marker["section"])


def compare(block):
    expected, problem = expected_output(block["marker"])
    if problem is not None:
        return "%s:%d %s" % (block["source"], block["line"], problem)
    if expected == block["body"]:
        return None
    return "%s:%d is not what the command prints\n%s" % (block["source"], block["line"],
                                                         diff_report(expected, block["body"]))


def diff_report(expected, found):
    expected_lines = expected.split("\n")
    found_lines = found.split("\n")
    report = []
    for index in range(max(len(expected_lines), len(found_lines))):
        left = expected_lines[index] if index < len(expected_lines) else "<block ends>"
        right = found_lines[index] if index < len(found_lines) else "<block ends>"
        if left != right:
            report.append("  line %d\n    stdout: %r\n    block : %r" % (index + 1, left, right))
    return "\n".join(report[:8])


def unmarked_report_fences(text, source):
    found = []
    for block in fenced_blocks(text):
        if block["marker"] is not None:
            continue
        for line in block["body"].split("\n"):
            for header in REPORT_HEADERS:
                if line.startswith(header):
                    found.append("%s:%d unmarked fence prints %r" % (source, block["line"], header))
    return found


class MarkerTests(unittest.TestCase):
    def test_the_documentation_still_carries_marked_samples(self):
        blocks = all_marked_blocks()

        self.assertGreaterEqual(len(blocks), MINIMUM_SAMPLES,
                                "only %d marked samples were found; removing a marker is how a "
                                "sample stops being checked" % len(blocks))

    def test_every_marker_names_a_script_and_a_target_that_exist(self):
        problems = []
        for block in all_marked_blocks():
            problems.extend(marker_problems(block))

        self.assertEqual(problems, [])

    def test_a_marker_must_sit_against_a_fence(self):
        text = "<!-- docdna:sample cmd=\"python3 x.py TARGET\" target=\".\" -->\n\nprose only\n"

        self.assertEqual(marked_blocks(text, "synthetic.md"), [])

    def test_an_unmarked_fence_is_skipped_rather_than_run(self):
        text = "```sh\ncp -R tests/fixtures/internal_service /tmp/svc\n```\n"
        blocks = fenced_blocks(text)

        self.assertEqual(len(blocks), 1)
        self.assertIsNone(blocks[0]["marker"])
        self.assertEqual(marked_blocks(text, "synthetic.md"), [])

    def test_an_unmarked_fence_is_skipped_next_to_a_marked_one(self):
        text = ("```sh\nls\n```\n\n"
                "<!-- docdna:sample cmd=\"python3 skill/scripts/docdna_scan.py TARGET\" "
                "target=\".\" -->\n"
                "```\nsample\n```\n\n"
                "```\nplain prose block\n```\n")
        blocks = marked_blocks(text, "synthetic.md")

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["body"], "sample")
        self.assertEqual(len(fenced_blocks(text)), 3)

    def test_an_indented_fence_is_read_without_its_indent(self):
        text = "1. step\n\n   ```sh\n   python3 thing.py\n   ```\n"
        blocks = fenced_blocks(text)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["body"], "python3 thing.py")
        self.assertTrue(blocks[0]["closed"])

    def test_a_marker_missing_its_target_is_a_failure(self):
        text = "<!-- docdna:sample cmd=\"python3 skill/scripts/docdna_scan.py TARGET\" -->\n```\nx\n```\n"
        block = marked_blocks(text, "synthetic.md")[0]

        self.assertTrue(any("no target" in problem for problem in marker_problems(block)))

    def test_a_marker_naming_a_missing_script_is_a_failure(self):
        text = ("<!-- docdna:sample cmd=\"python3 skill/scripts/docdna_ghost.py TARGET\" "
                "target=\".\" -->\n```\nx\n```\n")
        block = marked_blocks(text, "synthetic.md")[0]

        self.assertTrue(any("no script that exists" in problem
                            for problem in marker_problems(block)))

    def test_a_marker_naming_something_outside_the_scripts_directory_is_a_failure(self):
        text = ("<!-- docdna:sample cmd=\"python3 install.sh TARGET\" target=\".\" -->\n"
                "```\nx\n```\n")
        block = marked_blocks(text, "synthetic.md")[0]

        self.assertTrue(any("outside skill/scripts" in problem
                            for problem in marker_problems(block)))


class SectionTests(unittest.TestCase):
    STDOUT = "header\n  a: 1\n  b: 2\n\nnext section\n  c: 3"

    def test_a_section_runs_from_its_header_to_the_blank_line(self):
        body, problem = section_of(self.STDOUT, "header")

        self.assertIsNone(problem)
        self.assertEqual(body, "header\n  a: 1\n  b: 2")

    def test_a_section_that_is_not_printed_is_a_failure(self):
        body, problem = section_of(self.STDOUT, "not printed")

        self.assertIsNone(body)
        self.assertIn("no section headed", problem)

    def test_a_header_that_is_not_at_a_section_boundary_is_a_failure(self):
        body, problem = section_of("prose\nheader\n  a: 1\n", "header")

        self.assertIsNone(body)
        self.assertIn("not the first line", problem)

    def test_a_repeated_header_is_a_failure(self):
        body, problem = section_of("header\n  a: 1\n\nheader\n  b: 2\n", "header")

        self.assertIsNone(body)
        self.assertIn("ambiguous", problem)


class SampleTests(unittest.TestCase):
    def test_every_marked_sample_is_byte_identical_to_real_stdout(self):
        problems = []
        checked = 0
        for block in all_marked_blocks():
            checked += 1
            problem = compare(block)
            if problem is not None:
                problems.append(problem)

        self.assertGreaterEqual(checked, MINIMUM_SAMPLES)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_no_unmarked_fence_prints_a_report_section(self):
        problems = []
        for rel in DOCUMENTS:
            problems.extend(unmarked_report_fences(read_document(rel), rel))

        self.assertEqual(problems, [], "\n".join(problems))


class MutationTests(unittest.TestCase):
    def sample(self):
        for block in all_marked_blocks():
            if block["marker"].get("section"):
                return block
        raise AssertionError("no sectioned sample is available to mutate")

    def whole_run_sample(self):
        for block in all_marked_blocks():
            if not block["marker"].get("section"):
                return block
        raise AssertionError("no whole-run sample is available to mutate")

    def mutate(self, block, body):
        copy = dict(block)
        copy["body"] = body
        return copy

    def test_a_deleted_row_fails(self):
        for block in (self.sample(), self.whole_run_sample()):
            lines = block["body"].split("\n")
            for index in range(1, len(lines)):
                shorter = "\n".join(lines[:index] + lines[index + 1:])
                problem = compare(self.mutate(block, shorter))

                self.assertIsNotNone(problem, "deleting line %d of %s:%d went unnoticed"
                                     % (index + 1, block["source"], block["line"]))

    def test_a_single_changed_character_fails(self):
        for block in (self.sample(), self.whole_run_sample()):
            body = block["body"]
            spot = min(index for index, char in enumerate(body) if char.isalpha())
            changed = body[:spot] + ("z" if body[spot] != "z" else "q") + body[spot + 1:]
            problem = compare(self.mutate(block, changed))

            self.assertIsNotNone(problem, "a changed character in %s:%d went unnoticed"
                                 % (block["source"], block["line"]))

    def test_an_appended_row_fails(self):
        block = self.sample()
        problem = compare(self.mutate(block, block["body"] + "\n  ghost    : 1 signals unknown"))

        self.assertIsNotNone(problem)

    def test_trailing_whitespace_fails(self):
        block = self.sample()
        problem = compare(self.mutate(block, block["body"] + " "))

        self.assertIsNotNone(problem)

    def test_the_unmutated_sample_passes(self):
        for block in (self.sample(), self.whole_run_sample()):
            self.assertIsNone(compare(block))


if __name__ == "__main__":
    unittest.main()
