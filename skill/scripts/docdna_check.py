#!/usr/bin/env python3
"""Check repository documentation for drift, evidence, prose, hygiene, gaps, and lifecycle."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone

SCHEMA = 1
TOOL = "docdna_check"
VERSION = "1.4.0"

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_DIR = os.path.normpath(os.path.join(HERE, "..", "catalog"))
SCAN_SCRIPT = os.path.join(HERE, "docdna_scan.py")
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from docdna_fs import (FileTooLarge, MAX_CONTROL_BYTES, bind_root as safe_bind_root,
                       control_file_exists as safe_control_file_exists,
                       is_dir as safe_is_dir, is_file as safe_is_file,
                       listdir as safe_listdir, open_root as safe_open_root,
                       path_exists as safe_path_exists,
                       parse_json as safe_parse_json,
                       read_bounded_path as safe_read_bounded_path, read_text as safe_read_text,
                       require_config as safe_require_config,
                       require_manifest as safe_require_manifest,
                       require_root_identity as safe_require_root_identity,
                       require_scan as safe_require_scan,
                       root_is_current as safe_root_is_current,
                       walk_paths as safe_walk_paths,
                       write_text as safe_write_text)
from docdna_claims import (BIND_LINES, GAP_QUOTE, GAP_REACH, MAX_SPANS, PROVENANCE_REGIONS,
                           SHA_VALUE, TIGHT_STAGES, anchor_spans, as_list, claim_blocks,
                           covers_state as shared_covers_state, extract_declarations, gap_reach,
                           inside_repo, outside_repo, provenance_support as derived_provenance,
                           strip_citations, unsupported_numbers, window_around)
from docdna_prose import iter_findings as inspect_prose
from docdna_unicode import clean_generated_text, iter_findings as inspect_unicode

MANIFEST_REL = os.path.join(".docdna", "manifest.json")
CONFIG_REL = os.path.join(".docdna", "config.json")
META_REL = os.path.join(".docdna", "meta")
REPORT_REL = "DOCDNA.md"

GAPS_START = "<!-- docdna:gaps:start -->"
GAPS_END = "<!-- docdna:gaps:end -->"

PASSES = ("drift", "lint", "prose", "hygiene", "gaps", "spine", "tripwires", "orphans")
FAIL_ON = ("blocker", "major", "minor", "never")
SEVERITY_RANK = {"info": 0, "minor": 1, "major": 2, "blocker": 3}
GATE_RANK = {"blocker": 3, "major": 2, "minor": 1, "never": 99}

STATUS_ENUM = ("draft", "active", "deprecated", "superseded", "retired", "not-applicable")
DERIVATION_ENUM = ("derived", "drafted", "stub", "human-authored")
CONFIDENCE_ENUM = ("high", "medium", "low")
DURABILITY_ENUM = ("durable", "evidence", "transient")
SCOPE_ENUM = ("repo", "product", "org")
RECORD_ENUM = ("repo", "external", "ask")
CLASSIFICATION_ENUM = ("unclassified", "protected-a", "protected-b", "internal", "confidential")
GAP_KIND_ENUM = ("human-input", "not-implemented", "unverifiable", "out-of-scope", "stale-evidence")
# A citation that leaves the repository under analysis is refused, not downgraded, and it is
# refused at the same weight docdna_backfill.py --verify refuses it, so the two tools agree about
# which files are evidence. Every other citation problem stays where it was.
CITE_SEVERITY = {"path-outside-repo": "blocker"}
GAP_SEV_ENUM = ("blocker", "major", "minor")

REQUIRED_KEYS = ("id", "title", "stage", "status", "owner", "last_reviewed", "covers", "derivation")
KNOWN_KEYS = ("id", "instance_id", "title", "stage", "durability", "scope", "system_of_record",
              "classification", "status", "owner", "owner_candidate", "reviewed_by",
              "last_reviewed", "review_cadence", "next_review", "retention", "valid_until",
              "supersedes", "superseded_by", "not_applicable_reason", "retired_on", "covers",
              "covers_digest", "drift_budget", "last_validated_commit", "applies_to", "satisfies",
              "audiences", "traces_up", "traces_down", "derivation", "confidence", "retro",
              "generated_by", "generated_on", "content_hash", "open_questions")
ADOPTION_KEYS = ("covers", "stage", "generated_by", "derivation", "covers_digest")
DOCDNA_HINT = re.compile(r"(?m)^\s*(covers|covers_digest|drift_budget|derivation|generated_by)\s*:"
                         r"|docdna")

CADENCE_WORDS = ("none", "on-change", "on-release")
CADENCE_ISO = re.compile(r"^P(?=\w)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TIGHT_BUDGET = 1
LOOSE_BUDGET = 3
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GLOB_CHARS = "*?[]{}"
REF_AGE_DAYS = 365

IGNORE_DIRS = {".git", "node_modules", "dist", "build", "out", "target", "vendor", ".next",
               ".svelte-kit", "venv", ".venv", "__pycache__", "coverage", ".terraform",
               ".mypy_cache", ".pytest_cache", ".gradle", "Pods"}
SOURCE_EXT = {".c", ".cfg", ".cjs", ".conf", ".cpp", ".cs", ".css", ".ex", ".exs", ".go",
              ".graphql", ".h", ".hcl", ".html", ".ini", ".java", ".js", ".json", ".jsx", ".kt",
              ".lua", ".mjs", ".php", ".pl", ".prisma", ".proto", ".py", ".rb", ".rs",
              ".scala", ".sh", ".sql", ".svelte", ".swift", ".tf", ".toml", ".ts", ".tsx", ".vue",
              ".xml", ".yaml", ".yml"}
MAX_SOURCE_FILES = 4000
MAX_FILE_BYTES = 1000000
MARKDOWN_EXT = (".md", ".markdown")
TEXT_DOC_EXT = MARKDOWN_EXT + (".rst", ".adoc", ".txt")
MAX_PROSE_FINDINGS = 1000
MAX_HYGIENE_FINDINGS = 1000

ANNOTATION = re.compile(r"@covers\s+([A-Za-z][A-Za-z0-9_:@/#.\-]*)")
SPINE_ID = re.compile(r"^(?:bc|prd|req|adr|rsk|thr|ctl|tc|pm|inc|abuse-case|waiver)-[\w.\-]+$"
                      r"|^[a-z]+:\S+$")
SPINE_SPECS = [("delivery", "req", "tc"), ("assurance", "ctl", "evidence"), ("abuse", "thr", "tc")]
NO_ANNOTATIONS = "no annotations found"
DESCENDANTS = {"req": ("tc-", "test:"), "thr": ("tc-", "test:"), "ctl": ("evidence:",),
               "adr": ("module:",), "pm": ("adr-", "tc-")}
EXTERNAL_PREFIXES = ("epic:", "story:", "rel:", "assessment:", "evidence:", "waiver-",
                     "abuse-case-", "mitigation:")
PATH_PREFIXES = ("module:", "test:")

GAP_COMMENT = re.compile(r"<!--\s*GAP\s+(.*?)-->", re.S)
GAP_FIELD = re.compile(r"([A-Za-z_]+)=(\"[^\"]*\"|'[^']*'|\S+)")
CITE_PARTS = re.compile(r"\[`([^`\]]+)`(?:\s+\"([^\"]+)\")?\]")
CITE_RUN = re.compile(r"\[run:\s")
CITE_RUN_PARTS = re.compile(r"\[run:\s*`([^`]+)`\s*->\s*([^\]]+)\]")
CITE_REF = re.compile(r"\[ref:\s")
CITE_HUMAN = re.compile(r"\[human:\s")
CITE_REF_PARTS = re.compile(r"\[ref:\s*([^\]]*)\]")
CITE_HUMAN_PARTS = re.compile(r"\[human:\s*([^\]]*)\]")
HUMAN_FORM = re.compile(r"^(@\S+)\s+(\d{4}-\d{2}-\d{2})$")
CITE_LINE = re.compile(r"\[`[^`\]]*(?::\d+|#L\d+)`")
REF_VERIFIED = re.compile(r"\[ref:[^\]]*?verified\s+(\d{4}-\d{2}-\d{2})")
SLUG_CHARS = re.compile(r"[^a-z0-9]+")
LINK_TARGET = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
CONTROL_ROW = re.compile(r"^\|\s*([A-Za-z ]+?)\s*\|\s*(.*?)\s*\|$")
CONTROL_HEADING = "document control"

NUMBER_TERMS = re.compile(r"(?i)\b(rtos?|rpos?|slas?|slos?|mttr|mtbf|error budget|availability|"
                          r"uptime|downtime|latency|throughput|capacity|retention|retained|"
                          r"recovery time objective|recovery point objective|support window|"
                          r"end of support|end of life|end-of-life|eol|sunset|nines|"
                          r"review cadence|rate limits?|quotas?|response time|resolution time)\b")
NUMBER_DIGITS = r"\d[\d,_]*(?:\.\d+)?"
NUMBER_VALUES = [("a percentage",
                  re.compile(r"(?i)(?<![\w.])" + NUMBER_DIGITS + r"\s*(?:%|percent\b|pct\b)")),
                 ("a currency amount",
                  re.compile(r"(?i)[$\u00a3\u20ac]\s?" + NUMBER_DIGITS +
                             r"|(?<![\w.])" + NUMBER_DIGITS +
                             r"\s*(?:usd|eur|gbp|cad|aud|dollars?|euros?)\b")),
                 ("a duration",
                  re.compile(r"(?i)(?<![\w.])" + NUMBER_DIGITS +
                             r"[\s-]*(?:ms|milliseconds?|seconds?|secs?|minutes?|mins?|hours?|"
                             r"hrs?|business days?|days?|weeks?|months?|quarters?|years?)\b")),
                 ("an ISO 8601 duration", re.compile(r"\bP(?:\d+[YMWD])+(?:T(?:\d+[HMS])+)?\b")),
                 ("a date", re.compile(r"(?<![\w-])20\d\d(?:-\d\d-\d\d)?(?![\d-])")),
                 ("a number", re.compile(r"(?<![\w.])" + NUMBER_DIGITS))]
# What may sit between a commitment term and the value it claims. Only a connective: a copula, a
# preposition, a determiner, a hedge, or the noun a commitment is habitually written with. A verb
# that reports where something is written ("described in", "discussed in", "named in") is not here,
# which is the whole of the difference between "the RTO is 4 hours" and "the RTO is stated in
# section 4". A sentence terminator is not here either, so the pair never spans two sentences.
NUMBER_JOIN_WORD = (r"(?:is|are|was|were|be|been|of|at|to|for|from|by|as|on|per|the|a|an|its|our|"
                    r"their|this|that|about|approximately|roughly|around|target|targets|targeted|"
                    r"goal|objective|window|period|budget|policy|limit|threshold|value|set|sets|"
                    r"stands|stays|remains|holds|measured|measures|meets|met|sits|runs|ends|"
                    r"expires|until|through|under|below|over|above|within|up|least|most|more|"
                    r"than|exceeds|guaranteed|guarantees|guarantee|committed|commits|commit|"
                    r"currently|today|defined|configured|capped|limited|kept|held)")
NUMBER_JOIN_PUNCT = r"[\s:=~<>`'\"*_,()\[\]-]"
NUMBER_JOIN = re.compile(r"(?i)(?:%s+|%s\b)*" % (NUMBER_JOIN_PUNCT, NUMBER_JOIN_WORD))
NUMBER_JOIN_CELL = re.compile(r"(?i)(?:[|]|%s+|%s\b)*" % (NUMBER_JOIN_PUNCT, NUMBER_JOIN_WORD))
NUMBER_JOIN_CHARS = 40
# A pointer into a document is never a commitment, however close it sits to the word RTO.
NUMBER_STRUCTURAL = re.compile(r"(?i)\b(?:sections?|chapters?|steps?|figs?|figures?|tables?|"
                               r"annexe?s?|appendix|appendices|parts?|items?|pages?|lines?|"
                               r"notes?|rules?|clauses?|paragraphs?|footnotes?|versions?|v|"
                               r"phases?|tiers?|levels?|rounds?|questions?)"
                               r"[\s:.#-]{0,3}$")
# A count of the things in a repository is a fact about the tree, not a value a person decided.
NUMBER_COUNTED = re.compile(r"(?i)^[\s`'\"]*(?:configuration\s+|config\s+)?"
                            r"(?:files?|endpoints?|documents?|docs?|tests?|contributors?|"
                            r"repositories|repos?|services?|scripts?|modules?|packages?)\b")
# The opposite of a commitment. "no rate limit", "none of them sets an SLA", "does not state an
# RTO" all read as an SLA sentence to a bag of words and as a refusal to anybody else.
NUMBER_NEGATION = re.compile(r"(?i)\b(?:no|not|never|none|neither|nor|without|nothing|cannot|"
                             r"lacks?|lacking|absent|unspecified|unstated|undefined|unknown|"
                             r"missing)\b|n't\b")
NUMBER_NEGATION_REACH = 6
NUMBER_SENTENCE = re.compile(r"[.!?][\"'`)\]]*\s")
# A whole sentence set in quotation marks inside surrounding prose is being shown, not asserted.
# This is what a document that explains the number rule looks like, and flagging it made check
# accuse its own antipatterns page of stating a retention policy.
NUMBER_ILLUSTRATION = re.compile(r"\"[^\"\n]{1,240}?[.!?]\"")
NUMBER_MAX_TERMS = 40
NUMBER_MAX_VALUES = 80
CELL_KINDS = ("row", "label")
NUMBER_NOTE = ("a number is copied from the place a cited file states it, or it is a human-input "
               "GAP; check flags it for a person and never edits the prose")
NUMBER_REGION = ("every line after the frontmatter is read, and a fence joins the block that "
                 "introduces it; the one region skipped is an HTML comment, which renders to "
                 "nobody. This is the claim region docdna_backfill.py --verify reads, line for "
                 "line. No line is exempt. The banner and the rows under '## Document control' "
                 "are docdna's own provenance, so they answer to the run stamp, the tool version, "
                 "the GAP count and the frontmatter values docdna derived rather than to "
                 "citations; a number in one that docdna did not derive is reported like any "
                 "other. The frontmatter itself is the one thing check does not read for numbers, "
                 "because it is a contract a hand-written document never signed; "
                 "docdna_backfill.py --verify recomputes retention, valid_until, next_review, "
                 "drift_budget, review_cadence and the title from the catalog and refuses every "
                 "one it did not derive.")
NUMBER_DIFFERENCE = ("docdna_backfill.py --verify is stricter on the same lines: it refuses every "
                     "unsupported number as a blocker, because it is judging text docdna is about "
                     "to write, and it reads the frontmatter as well. check flags one shape and "
                     "reports the rest to nobody: a commitment term (RTO, RPO, SLA, SLO, MTTR, "
                     "availability, uptime, latency, throughput, capacity, retention, rate limit, "
                     "quota, error budget, review cadence, support window, end of life) joined to "
                     "the value it claims (a percentage, a currency amount, a duration, an ISO "
                     "8601 duration, a date, or a bare literal) by nothing but a connective, "
                     "inside one sentence. A number check passes can still be refused by "
                     "--verify.")
NUMBER_MISSES = ("what the number rule does not catch, stated so nobody reads it as tighter than "
                 "it is. A commitment split across two sentences ('The RTO was decided last "
                 "quarter. It is 4 hours.') is not read as one, because binding across a sentence "
                 "boundary is what made check accuse 'latency is discussed in chapter 4'. A "
                 "commitment written with a term this list does not carry, or spelled out in "
                 "words rather than digits ('four hours'), is not read at all. A structural "
                 "pointer (section 2, table 3, step 5), a count of files or endpoints, and a term "
                 "under negation ('no rate limit', 'none of them sets an SLA') are excluded by "
                 "rule, so a real commitment phrased as one of those is missed by the same rule. "
                 "A whole sentence set in quotation marks inside surrounding prose is read as an "
                 "example being shown rather than a claim being made. docdna_backfill.py --verify "
                 "reads none of these exclusions and refuses every unsupported number in text "
                 "docdna itself writes, which is where the coverage that matters lives.")
NUMBER_BINDING = ("a citation names a place, so it backs the numbers written within %d lines of "
                  "the symbol or anchor it names and no others. A citation that names a file and "
                  "no place inside it resolves and binds nothing, because a constants module is "
                  "not a source for every figure in the tree." % BIND_LINES)
RUN_NOTE = ("docdna is read only and never executes a command, so the output written beside a run "
            "citation is the author's own text. It is recorded as self-attested, it supports no "
            "number, and a document carrying one is never reported as clean.")
HUMAN_NOTE = ("a human citation is a person putting their handle on a number rather than the "
              "repository stating it, so the block is recorded as attested and never as verified.")
NON_ADOPTED_NOTE = ("this document carries no docdna frontmatter, so nothing here was derived "
                    "under a covers contract; the number is reported at minor and gates only "
                    "under --fail-on minor")

OWNER_NOTE = "owner: unassigned is an open question for a person, never a check failure"
UNVERIFIABLE_NOTE = ("covers is empty, which is the honest state for frame and govern documents "
                     "and is never a failure")


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today():
    return datetime.now(timezone.utc).date()


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def repository_path(root, candidate):
    prefix = os.path.abspath(root)
    prefix_real = os.path.realpath(prefix)
    target = (os.path.abspath(candidate) if os.path.isabs(candidate)
              else os.path.abspath(os.path.join(prefix, candidate)))
    try:
        if os.path.commonpath([prefix, target]) != prefix:
            return None
        resolved = os.path.realpath(target)
        if os.path.commonpath([prefix_real, resolved]) != prefix_real:
            return None
    except ValueError:
        return None
    return resolved


def read_text(root, path):
    candidate = repository_path(root, path)
    if candidate is None:
        return None
    try:
        text = safe_read_text(root, candidate, errors="replace", max_bytes=MAX_FILE_BYTES)
    except (OSError, ValueError, FileTooLarge):
        return None
    if "\x00" in text:
        return None
    return text


def run_git(root, args):
    if not safe_root_is_current(root):
        return None
    descriptor = safe_open_root(root)

    def enter_bound_root():
        os.fchdir(descriptor)

    try:
        process = subprocess.run(["git"] + args, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, timeout=60,
                                 preexec_fn=enter_bound_root, pass_fds=(descriptor,))
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        os.close(descriptor)
    if process.returncode != 0 or not safe_root_is_current(root):
        return None
    return process.stdout.decode("utf-8", "replace")


def commit_name(value):
    # last_validated_commit is frontmatter, so it is text the document controls. Only a hex object
    # name reaches git: anything else, an option such as --output=PATH included, is unresolvable.
    return isinstance(value, str) and SHA_VALUE.match(value) is not None


def git_show(root, commit, rel):
    if not commit_name(commit) or not isinstance(rel, str):
        return None
    return run_git(root, ["show", "%s:%s" % (commit, rel)])


def parse_date(value):
    if not isinstance(value, str) or not DATE_RE.match(value.strip()):
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def duration_days(value):
    if not isinstance(value, str):
        return None
    match = CADENCE_ISO.match(value.strip())
    if not match:
        return None
    years, months, weeks, days = match.group(1), match.group(2), match.group(3), match.group(4)
    total = 0
    total += int(years[:-1]) * 365 if years else 0
    total += int(months[:-1]) * 30 if months else 0
    total += int(weeks[:-1]) * 7 if weeks else 0
    total += int(days[:-1]) if days else 0
    return total or None


def scalar(raw):
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.endswith(","):
        text = text[:-1].strip()
    lower = text.lower()
    if lower in ("null", "~", ""):
        return None
    if lower == "true":
        return True
    if lower == "false":
        return False
    if re.match(r"^-?\d+$", text):
        return int(text)
    return text


def parse_block(lines, start, end):
    data = {}
    order = []
    key = None
    for number in range(start, end):
        stripped = lines[number].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if lines[number][:1] in (" ", "\t") and not stripped.startswith("- "):
            return None, ("nested mapping on line %d is outside the restricted grammar of flat "
                          "keys, simple lists, and one level" % (number + 1))
        if stripped.startswith("- "):
            if key is None:
                return None, "list item before any key on line %d" % (number + 1)
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(scalar(stripped[2:]))
            continue
        match = re.match(r"^([A-Za-z0-9_.\-]+):\s*(.*)$", stripped)
        if not match:
            return None, "unparsable line %d: %s" % (number + 1, stripped[:60])
        key = match.group(1)
        value = match.group(2).strip()
        if key not in order:
            order.append(key)
        if not value:
            data[key] = []
        elif value.startswith("[") and value.endswith("]"):
            data[key] = [scalar(part) for part in value[1:-1].split(",") if part.strip()]
        else:
            data[key] = scalar(value)
    data["__order__"] = order
    return data, None


def parse_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False, None, None, 0
    end = None
    for number in range(1, len(lines)):
        if lines[number].strip() in ("---", "..."):
            end = number
            break
    if end is None:
        return True, None, "unterminated frontmatter block", 0
    data, error = parse_block(lines, 1, end)
    return True, data, error, end + 1


def frontmatter_raw(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    kept = []
    for line in lines[1:101]:
        if line.strip() in ("---", "..."):
            break
        kept.append(line)
    return "\n".join(kept)


def parse_sidecar(text):
    lines = text.splitlines()
    start = 1 if lines and lines[0].strip() == "---" else 0
    end = len(lines)
    for number in range(start, len(lines)):
        if start and lines[number].strip() in ("---", "..."):
            end = number
            break
    return parse_block(lines, start, end)


def validate_metadata_identities(data):
    # Replace invalid identity values before any pass can use them as mapping keys.
    clean = dict(data)
    errors = []
    ident = clean.get("id")
    if ident is not None and not isinstance(ident, str):
        errors.append("id must be a string, not %s" % type(ident).__name__)
        clean["id"] = None
    instance = clean.get("instance_id")
    if instance is not None and not isinstance(instance, str):
        errors.append("instance_id must be a string or null, not %s"
                      % type(instance).__name__)
        clean["instance_id"] = None
    return clean, "; ".join(errors) if errors else None


def covers_state(root, covers, commit=None):
    # docdna_claims.covers_state, the one computation docdna_backfill.py stamps into the
    # frontmatter it plans. With a commit, every covered file is read as it stood at that commit.
    if commit is None:
        return shared_covers_state(root, covers)
    return shared_covers_state(root, covers, lambda rel: git_show(root, commit, rel))


def document_blocks(doc):
    return claim_blocks(doc["lines"], doc["body_start"])


def body_blocks(blocks):
    return [block for block in blocks if block["region"] not in PROVENANCE_REGIONS]


def claim_coverage(blocks):
    # What a citation is asked to cover: prose a person wrote as an assertion. The banner and the
    # document control table are docdna's own provenance and are checked against what docdna
    # derived instead, and a heading, a table header row and the confidence line are labels rather
    # than claims. Every one of them is still read by the number rule.
    return [block for block in body_blocks(blocks)
            if block["kind"] in ("paragraph", "bullet", "row", "fence")]


def cited(ctx, text):
    # A code citation names a place, with a symbol or a verbatim anchor, or it names a file that
    # resolves inside the repository. A bracketed code span that does neither, such as [`TODO`],
    # is formatting, and counting it as a citation let any block pass the coverage rule with one.
    if CITE_RUN.search(text) or CITE_REF.search(text) or CITE_HUMAN.search(text):
        return True
    for match in CITE_PARTS.finditer(text):
        rel, anchor = code_target(match)
        if anchor or (rel and code_file(ctx, rel)):
            return True
    return False


def gap_records(text, path):
    records = []
    errors = []
    for match in GAP_COMMENT.finditer(text):
        fields = {}
        for field in GAP_FIELD.finditer(match.group(1)):
            fields[field.group(1)] = scalar(field.group(2))
        line = text.count("\n", 0, match.start()) + 1
        record = {"id": fields.get("id"), "kind": fields.get("kind"), "sev": fields.get("sev"),
                  "owner": fields.get("owner") or "unassigned", "doc": fields.get("doc"),
                  "asks": fields.get("asks"), "path": path, "line": line, "quoted": False}
        records.append(record)
    quotes = {}
    for number, line in enumerate(text.splitlines(), 1):
        match = GAP_QUOTE.match(line.strip())
        if match:
            quotes[match.group(1)] = {"line": number, "sev": match.group(2)}
    seen = {}
    for record in records:
        ident = record["id"]
        if ident is None:
            errors.append((record["line"], "GAP comment has no id"))
            continue
        if ident in seen:
            errors.append((record["line"], "GAP %s is declared twice" % ident))
        seen[ident] = record
        if ident in quotes:
            record["quoted"] = True
            quoted_sev = quotes[ident]["sev"]
            if quoted_sev and record["sev"] and quoted_sev != record["sev"]:
                errors.append((record["line"], "GAP %s comment says sev=%s and the blockquote says "
                                               "(%s)" % (ident, record["sev"], quoted_sev)))
        else:
            errors.append((record["line"], "GAP %s has no reader-visible blockquote half" % ident))
        if record["kind"] not in GAP_KIND_ENUM:
            errors.append((record["line"], "GAP %s kind=%s is outside the enum: %s"
                           % (ident, record["kind"], ", ".join(GAP_KIND_ENUM))))
        if record["sev"] not in GAP_SEV_ENUM:
            errors.append((record["line"], "GAP %s sev=%s is outside the enum: %s"
                           % (ident, record["sev"], ", ".join(GAP_SEV_ENUM))))
        if not record["asks"]:
            errors.append((record["line"], "GAP %s has no quoted asks= sentence" % ident))
    for ident in sorted(quotes):
        if ident not in seen:
            errors.append((quotes[ident]["line"], "blockquote GAP %s has no machine-readable "
                                                  "comment half" % ident))
    return records, errors


def control_values(lines):
    values = {}
    inside = False
    for line in lines:
        stripped = line.strip()
        heading = HEADING.match(stripped)
        if heading:
            inside = heading.group(1).strip().lower().startswith(CONTROL_HEADING)
            continue
        if not inside or not stripped.startswith("|"):
            continue
        match = CONTROL_ROW.match(stripped)
        if match:
            values[match.group(1).strip().lower()] = match.group(2).strip()
    return values


def relative_links(root, rel, text):
    broken = []
    base = os.path.dirname(os.path.join(root, rel))
    for match in LINK_TARGET.finditer(text):
        target = match.group(1).strip()
        if not target or "://" in target or target.startswith(("#", "mailto:", "tel:")):
            continue
        clean = target.split("#", 1)[0].split("?", 1)[0]
        if not clean:
            continue
        full = os.path.normpath(os.path.join(base, clean))
        if not safe_path_exists(root, full):
            line = text.count("\n", 0, match.start()) + 1
            broken.append((line, target))
    return broken


def load_catalog_documents():
    path = os.path.join(CATALOG_DIR, "documents.json")
    entries = {}
    for entry in load_json(path)["documents"]:
        entries[entry["id"]] = entry
    return entries


def load_manifest(root):
    if not safe_path_exists(root, MANIFEST_REL):
        return None
    try:
        text = safe_read_text(root, MANIFEST_REL, max_bytes=MAX_CONTROL_BYTES)
    except FileTooLarge:
        raise
    except (OSError, ValueError):
        return None
    manifest = safe_parse_json(text, MANIFEST_REL)
    return safe_require_manifest(manifest, MANIFEST_REL, SCHEMA)


def load_config(root, manifest):
    config = {"assurance_set": [], "regulated": False, "safety_critical": False,
              "source": "defaults"}
    answers = {}
    for key, row in ((manifest or {}).get("interview") or {}).items():
        answers[key] = row.get("value")
    if answers.get("q3_authorizer") in ("soc2-or-iso-auditor", "government-authorizer",
                                        "sector-regulator"):
        config["regulated"] = True
    if answers.get("q6_downtime") == "revenue-or-safety-minutes":
        config["safety_critical"] = True
    if safe_control_file_exists(root, CONFIG_REL):
        text = safe_read_text(root, CONFIG_REL, max_bytes=MAX_CONTROL_BYTES)
        raw = safe_parse_json(text, CONFIG_REL)
        safe_require_config(raw, CONFIG_REL)
        config["source"] = CONFIG_REL
        config["assurance_set"] = [item for item in as_list(raw.get("assurance_set"))
                                   if isinstance(item, str)]
        for key in ("regulated", "safety_critical"):
            if key in raw:
                config[key] = bool(raw[key])
    return config


def config_excludes(repo):
    if not safe_control_file_exists(repo, CONFIG_REL):
        return []
    text = safe_read_text(repo, CONFIG_REL, max_bytes=MAX_CONTROL_BYTES)
    raw = safe_parse_json(text, CONFIG_REL)
    safe_require_config(raw, CONFIG_REL)
    return [item for item in as_list(raw.get("exclude_dirs")) if isinstance(item, str)]


def run_scan(repo, exclude_dirs=None):
    if not safe_root_is_current(repo):
        raise ValueError("repository root changed before docdna_scan.py ran")
    descriptor = safe_open_root(repo)

    def enter_bound_root():
        os.fchdir(descriptor)

    command = [sys.executable, SCAN_SCRIPT, "--json", "."]
    for directory in exclude_dirs or []:
        # One argv item, so a directory whose name starts with a dash is a value and never an option
        # docdna_scan.py's parser rejects.
        command.append("--exclude-dir=" + directory)
    try:
        with tempfile.TemporaryFile() as output:
            process = subprocess.run(command, stdout=output, stderr=subprocess.PIPE,
                                     preexec_fn=enter_bound_root, pass_fds=(descriptor,))
            output.seek(0)
            raw = output.read(MAX_CONTROL_BYTES + 1)
    finally:
        os.close(descriptor)
    if not safe_root_is_current(repo):
        raise ValueError("repository root changed while docdna_scan.py ran")
    if process.returncode != 0:
        raise ValueError("docdna_scan.py failed: %s"
                         % process.stderr.decode("utf-8", "replace").strip())
    if len(raw) > MAX_CONTROL_BYTES:
        raise ValueError("docdna_scan.py output exceeds the %d byte limit" % MAX_CONTROL_BYTES)
    return safe_parse_json(raw.decode("utf-8", "replace"), "docdna_scan.py output")


def adopted_frontmatter(data):
    if not isinstance(data, dict) or not data.get("id"):
        return False
    return any(key in data for key in ADOPTION_KEYS)


def collect_documents(root, scan):
    documents = []
    for row in scan["inventory"]["docs"]:
        rel = row["path"]
        if not rel.lower().endswith(MARKDOWN_EXT):
            continue
        if row.get("bytes") is None:
            continue
        text = read_text(root, rel)
        if text is None:
            continue
        present, data, error, body_start = parse_frontmatter(text)
        if not present:
            continue
        if error is not None:
            if DOCDNA_HINT.search(frontmatter_raw(text)):
                documents.append({"path": rel, "id": None, "data": {}, "error": error,
                                  "text": text, "lines": [], "body_start": 0, "sidecar": None,
                                  "kind": "markdown"})
            continue
        if not adopted_frontmatter(data):
            continue
        data, identity_error = validate_metadata_identities(data)
        documents.append({"path": rel, "id": data.get("id"), "data": data, "error": None,
                          "text": text, "lines": text.splitlines(), "body_start": body_start,
                          "sidecar": None, "kind": "markdown"})
        if identity_error:
            documents[-1]["error"] = identity_error
    for record in collect_sidecars(root):
        documents.append(record)
    documents.sort(key=lambda item: item["path"])
    return documents


def collect_prose(root, scan, documents):
    # Every Markdown document in the documentation set that docdna did not write. These are the
    # documents most likely to carry a number nobody can source, precisely because no covers
    # contract ever held them, and auditing human-authored documentation is what check is for.
    # They are linted, never adopted: they stay out of drift, spine, orphans and the gap register.
    adopted = set(doc["path"] for doc in documents)
    prose = []
    for row in scan["inventory"]["docs"]:
        rel = row["path"]
        if rel in adopted or not rel.lower().endswith(MARKDOWN_EXT):
            continue
        if row.get("bytes") is None:
            continue
        text = read_text(root, rel)
        if text is None:
            continue
        _, data, _, body_start = parse_frontmatter(text)
        prose.append({"path": rel, "id": None, "data": data or {}, "error": None, "text": text,
                      "lines": text.splitlines(), "body_start": body_start, "sidecar": None,
                      "kind": "prose"})
    prose.sort(key=lambda item: item["path"])
    return prose


def collect_sidecars(root):
    records = []
    if not safe_is_dir(root, META_REL):
        return records
    for name in sorted(safe_listdir(root, META_REL)):
        if not name.endswith((".yml", ".yaml")):
            continue
        rel = os.path.join(META_REL, name)
        text = read_text(root, rel)
        if text is None:
            continue
        data, error = parse_sidecar(text)
        if data is not None:
            data, identity_error = validate_metadata_identities(data)
            error = error or identity_error
        records.append({"path": rel, "id": (data or {}).get("id") or os.path.splitext(name)[0],
                        "data": data or {}, "error": error, "text": text, "lines": [],
                        "body_start": 0, "sidecar": os.path.splitext(name)[0],
                        "kind": "sidecar"})
    return records


def source_files(root):
    files = []
    def pruned(name, parent):
        return name in IGNORE_DIRS or name.startswith(".")

    indexed, _ = safe_walk_paths(root, pruned)
    for rel in indexed:
        if os.path.splitext(rel)[1].lower() in SOURCE_EXT and safe_is_file(root, rel):
            files.append(rel)
            if len(files) >= MAX_SOURCE_FILES:
                break
    return files


def collect_annotations(root):
    found = []
    for rel in source_files(root):
        text = read_text(root, rel)
        if text is None or "@covers" not in text:
            continue
        for match in ANNOTATION.finditer(text):
            target = match.group(1).rstrip(".,;:")
            if not SPINE_ID.match(target):
                continue
            line = text.count("\n", 0, match.start()) + 1
            found.append({"path": rel, "line": line, "target": target})
    return found


def signal_map(scan):
    signals = {}
    for row in scan.get("signals") or []:
        signals[row["id"]] = row
    return signals


def predicate(ctx, node):
    if not isinstance(node, dict) or not node:
        raise ValueError("predicate is not an object: %s" % json.dumps(node))
    if "all" in node:
        return all(predicate(ctx, child) for child in node["all"])
    if "any" in node:
        return any(predicate(ctx, child) for child in node["any"])
    if "not" in node:
        return not predicate(ctx, node["not"])
    if "always" in node:
        return bool(node["always"])
    if "never" in node:
        return not bool(node["never"])
    if "signal" in node:
        record = ctx["signals"].get(node["signal"])
        if record is None:
            raise ValueError("predicate names signal %s, absent from this scan" % node["signal"])
        if "gte" in node:
            return record["state"] == "present" and (record.get("hits") or 0) >= node["gte"]
        if "is" in node:
            return record["state"] == node["is"]
        return record["state"] == "present"
    if "answer" in node:
        value = ctx["answers"].get(node["answer"])
        if value is None:
            return False
        chosen = value if isinstance(value, list) else [value]
        wanted = node.get("in") or ([node["is"]] if "is" in node else [])
        return any(item in wanted for item in chosen)
    if "archetype" in node:
        return ctx["archetype"] == node["archetype"]
    if "overlay" in node:
        return node["overlay"] in ctx["overlays"]
    if "document" in node:
        state = ctx["docstate"].get(node["document"], "absent")
        wanted = node.get("state", "present")
        if wanted == "present":
            return state.startswith("present")
        return state == wanted
    raise ValueError("unknown predicate operator: %s" % ", ".join(sorted(node)))


def true_terms(ctx, node, out):
    if not isinstance(node, dict):
        return
    if "all" in node:
        for child in node["all"]:
            true_terms(ctx, child, out)
        return
    if "any" in node:
        for child in node["any"]:
            if predicate(ctx, child):
                true_terms(ctx, child, out)
        return
    if "not" in node:
        true_terms(ctx, node["not"], out)
        return
    for key in ("signal", "answer", "archetype", "overlay", "document"):
        if key in node and node[key] not in out:
            out.append(node[key])


def term_evidence(ctx, terms, limit=2):
    paths = []
    for token in terms:
        record = ctx["signals"].get(token)
        if record is None:
            continue
        for item in record.get("evidence") or []:
            path = item.get("path")
            if path and path not in paths:
                paths.append(path)
            if len(paths) >= limit:
                return paths
    return paths


def gates(ctx, pass_name, severity, ident):
    if severity == "info":
        return False
    if pass_name == "lint":
        return True
    if pass_name == "hygiene":
        return True
    if pass_name == "spine":
        return SEVERITY_RANK[severity] >= SEVERITY_RANK["major"]
    if pass_name == "drift":
        return bool(ident) and ident in ctx["config"]["assurance_set"]
    return False


def finding(ctx, pass_name, kind, severity, detail, path=None, ident=None, line=None, column=None):
    row = {"pass": pass_name, "kind": kind, "severity": severity, "detail": detail,
           "path": path, "id": ident, "line": line, "column": column,
           "gating": gates(ctx, pass_name, severity, ident)}
    ctx["findings"].append(row)
    return row


def budget_for(data):
    budget = data.get("drift_budget")
    if isinstance(budget, int) and budget >= 0:
        return budget, "frontmatter"
    if data.get("stage") in TIGHT_STAGES:
        return TIGHT_BUDGET, "stage default"
    return LOOSE_BUDGET, "default"


def digest_recorded(data):
    value = data.get("covers_digest")
    if not isinstance(value, str) or not value.strip():
        return None, "no covers_digest recorded"
    if not DIGEST_RE.match(value.strip()):
        return None, "covers_digest is not a full sha256 digest"
    return value.strip(), None


def declaration_delta(root, doc, covers, actual):
    commit = doc["data"].get("last_validated_commit")
    if not commit or not isinstance(commit, str):
        return None, None, ("frontmatter records no last_validated_commit, so there is no earlier "
                            "state to replay the previous declarations from")
    if not commit_name(commit):
        return None, None, ("last_validated_commit is not a hexadecimal commit name, so there is "
                            "no earlier state to replay the previous declarations from")
    previous = covers_state(root, covers, commit)
    if previous["digest"] != doc["recorded_digest"]:
        return None, None, ("last_validated_commit %s no longer reproduces the recorded "
                            "covers_digest, so the declaration delta cannot be counted"
                            % commit[:12])
    before = set(previous["entries"])
    after = set(actual["entries"])
    added = sorted(after - before)
    removed = sorted(before - after)
    return added, removed, None


def name_of(entry):
    return entry.split("#", 1)[1] if "#" in entry else entry


def citation_anchor(root, row):
    if row.get("kind") != "path-not-found":
        return False
    claim = row.get("claim") or ""
    if "#" not in claim:
        return False
    return safe_is_file(root, repository_path(root, claim.split("#", 1)[0])
                        or claim.split("#", 1)[0])


def pass_drift(ctx):
    root = ctx["root"]
    rows = []
    for row in ctx["scan"].get("drift") or []:
        if citation_anchor(root, row):
            continue
        ident = ctx["path_ids"].get(row["doc"])
        severity = "major" if row.get("confidence") == "high" else "minor"
        detail = "%s: %s" % (row.get("claim") or row["kind"], row.get("detail") or "")
        finding(ctx, "drift", "scanner-" + row["kind"], severity, detail.strip(),
                path=row["doc"], ident=ident, line=row.get("line"))
        rows.append(row)
    ctx["report"]["drift"] = {"scanner": rows, "digest": []}
    for doc in ctx["documents"]:
        if doc["error"] is not None:
            continue
        data = doc["data"]
        covers = as_list(data.get("covers"))
        ident = doc["id"]
        stale = {"calendar_stale": False, "drift_stale": False, "expiry_stale": False,
                 "unverifiable": not covers}
        record = {"id": ident, "path": doc["path"], "covers": covers, "staleness": stale,
                  "budget": None, "budget_applied": None, "changes": None, "added": None,
                  "removed": None, "digest_recorded": None, "digest_actual": None,
                  "method": None, "reason": None}
        reviewed = parse_date(data.get("last_reviewed"))
        cadence = data.get("review_cadence")
        window = duration_days(cadence) if isinstance(cadence, str) else None
        if reviewed is not None and window:
            age = (ctx["today"] - reviewed).days
            if age > window:
                stale["calendar_stale"] = True
                finding(ctx, "drift", "calendar-stale", "minor",
                        "last reviewed %s, %d days ago, cadence %s" % (reviewed, age, cadence),
                        path=doc["path"], ident=ident)
        expiry = parse_date(data.get("valid_until"))
        if expiry is not None and ctx["today"] > expiry:
            stale["expiry_stale"] = True
            finding(ctx, "drift", "expiry-stale", "major",
                    "valid_until %s has passed" % expiry, path=doc["path"], ident=ident)
        if not covers:
            record["reason"] = UNVERIFIABLE_NOTE
            finding(ctx, "drift", "unverifiable", "info", UNVERIFIABLE_NOTE,
                    path=doc["path"], ident=ident)
            ctx["report"]["drift"]["digest"].append(record)
            continue
        actual = covers_state(root, covers)
        recorded, problem = digest_recorded(data)
        doc["recorded_digest"] = recorded
        budget, origin = budget_for(data)
        record["budget"] = budget
        record["digest_actual"] = actual["digest"]
        record["digest_recorded"] = recorded
        record["files"] = actual["files"]
        record["missing"] = actual["missing"]
        if recorded is None:
            record["reason"] = problem
            record["method"] = "none"
            ctx["report"]["drift"]["digest"].append(record)
            continue
        if recorded == actual["digest"]:
            record["method"] = "digest"
            record["changes"] = 0
            ctx["report"]["drift"]["digest"].append(record)
            continue
        added, removed, problem = declaration_delta(root, doc, covers, actual)
        if problem is None:
            record["method"] = "git"
            record["budget_applied"] = True
            record["added"] = [name_of(item) for item in added]
            record["removed"] = [name_of(item) for item in removed]
            record["changes"] = len(added) + len(removed)
            fired = record["changes"] > budget
            detail = ("%d declaration changes over budget %d (%s); gone: %s; new: %s"
                      % (record["changes"], budget, origin,
                         ", ".join(record["removed"][:4]) or "none",
                         ", ".join(record["added"][:4]) or "none"))
        else:
            record["method"] = "digest"
            record["budget_applied"] = False
            record["reason"] = problem
            fired = True
            detail = ("drift_budget %d (%s) was NOT applied: %s. Declarations changed in %s and "
                      "the document is reported stale on the digest alone, so the budget is "
                      "inoperative until last_validated_commit is recorded again"
                      % (budget, origin, problem, ", ".join(covers[:3])))
        stale["drift_stale"] = fired
        if fired:
            finding(ctx, "drift", "drift-stale", "major", detail, path=doc["path"], ident=ident)
        ctx["report"]["drift"]["digest"].append(record)


def lint_covers(ctx, doc):
    data = doc["data"]
    covers = as_list(data.get("covers"))
    root = ctx["root"]
    for entry in covers:
        if not isinstance(entry, str):
            finding(ctx, "lint", "covers-type", "major", "covers entry is not a path: %s"
                    % json.dumps(entry), path=doc["path"], ident=doc["id"])
            continue
        if any(char in entry for char in GLOB_CHARS):
            finding(ctx, "lint", "covers-glob", "blocker",
                    "covers names a glob: %s. covers names interface-defining files, never "
                    "patterns; a glob saturates the drift test." % entry,
                    path=doc["path"], ident=doc["id"])
            continue
        if entry.endswith("/") or safe_is_dir(root, repository_path(root, entry) or entry):
            finding(ctx, "lint", "covers-directory", "blocker",
                    "covers names a directory: %s. covers names interface-defining files, never "
                    "directories; a directory saturates the drift test." % entry,
                    path=doc["path"], ident=doc["id"])
            continue
        if not safe_is_file(root, repository_path(root, entry) or entry):
            finding(ctx, "lint", "covers-missing", "major",
                    "covers names %s, which is not a file in this repository" % entry,
                    path=doc["path"], ident=doc["id"])
    if covers:
        recorded, problem = digest_recorded(data)
        if recorded is None:
            finding(ctx, "lint", "covers-digest", "minor",
                    "%s; drift cannot be measured for this document" % problem,
                    path=doc["path"], ident=doc["id"])


def lint_enums(ctx, doc):
    data = doc["data"]
    checks = [("status", STATUS_ENUM, "major"), ("derivation", DERIVATION_ENUM, "minor"),
              ("confidence", CONFIDENCE_ENUM, "minor"), ("durability", DURABILITY_ENUM, "minor"),
              ("scope", SCOPE_ENUM, "minor"), ("system_of_record", RECORD_ENUM, "minor"),
              ("classification", CLASSIFICATION_ENUM, "minor")]
    for key, enum, severity in checks:
        value = data.get(key)
        if value in (None, []) or key not in data:
            continue
        if value not in enum:
            finding(ctx, "lint", key + "-enum", severity,
                    "%s: %s is outside the enum: %s" % (key, value, ", ".join(enum)),
                    path=doc["path"], ident=doc["id"])
    cadence = data.get("review_cadence")
    if isinstance(cadence, str) and cadence not in CADENCE_WORDS and not CADENCE_ISO.match(cadence):
        finding(ctx, "lint", "cadence", "minor",
                "review_cadence: %s is neither %s nor an ISO 8601 duration"
                % (cadence, ", ".join(CADENCE_WORDS)), path=doc["path"], ident=doc["id"])
    for key in ("last_reviewed", "next_review", "valid_until", "generated_on", "retired_on"):
        value = data.get(key)
        if isinstance(value, str) and value and parse_date(value) is None:
            finding(ctx, "lint", "date", "minor", "%s: %s is not a YYYY-MM-DD date" % (key, value),
                    path=doc["path"], ident=doc["id"])


def lint_keys(ctx, doc):
    data = doc["data"]
    order = data.get("__order__") or list(data)
    for key in REQUIRED_KEYS:
        if key in data:
            continue
        severity = "blocker" if key == "id" else "major"
        finding(ctx, "lint", "missing-key", severity, "frontmatter has no %s" % key,
                path=doc["path"], ident=doc["id"])
    for key in order:
        if key != "__order__" and key not in KNOWN_KEYS:
            finding(ctx, "lint", "unknown-key", "minor",
                    "frontmatter key %s is not in the schema" % key,
                    path=doc["path"], ident=doc["id"])
    ident = doc["id"]
    if ident and ctx["catalog"] and ident not in ctx["catalog"]:
        finding(ctx, "lint", "unknown-id", "major",
                "id %s is not in catalog/documents.json" % ident,
                path=doc["path"], ident=None)


def lint_sidecars(ctx):
    if not ctx["adopted"]:
        return
    for ident, target in sorted(ctx["found_paths"].items()):
        if target.lower().endswith(MARKDOWN_EXT) or target.endswith("/"):
            continue
        if ident in ctx["sidecar_ids"] or not safe_is_file(
                ctx["root"], repository_path(ctx["root"], target) or target):
            continue
        finding(ctx, "lint", "sidecar-missing", "major",
                "%s is not Markdown, so its frontmatter has nowhere to go and needs a sidecar at "
                "%s/%s.yml" % (target, META_REL, ident), path=target, ident=ident)


def lint_body(ctx, doc):
    if doc["kind"] != "markdown":
        return
    blocks = document_blocks(doc)
    supports = block_support(ctx, doc, blocks)
    assertions = claim_coverage(blocks)
    total = len(assertions)
    marked = [cited(ctx, block["text"]) for block in assertions]
    covered = sum(1 for flag in marked if flag)
    gaps = ctx["gaps_by_path"].get(doc["path"]) or []
    doc["claims"] = {"blocks": total, "cited": covered, "gaps": len(gaps),
                     "numbers": lint_numbers(ctx, doc, blocks, supports)}
    doc["claims"].update(lint_attestations(ctx, doc, blocks, supports))
    human = doc["data"].get("derivation") == "human-authored"
    # A claim block that starts within GAP_REACH lines of a GAP marker is covered by it, the window
    # docdna_backfill.py --verify counts as gap-covered. The window shields the block from this rule
    # alone: lint_numbers has already read every number in it.
    reach = gap_reach(record["line"] for record in gaps)
    uncited = [block for block, flag in zip(assertions, marked)
               if not flag and block["line"] not in reach]
    if uncited:
        severity = "info" if human else "major"
        detail = ("%d of %d claim blocks carry neither a citation nor a GAP marker within %d "
                  "lines; first at line %d" % (len(uncited), total, GAP_REACH, uncited[0]["line"]))
        if human:
            detail += " (derivation: human-authored, so this is reported, not gated)"
        finding(ctx, "lint", "citation-coverage", severity, detail,
                path=doc["path"], ident=doc["id"], line=uncited[0]["line"])
    if not human and gaps and covered < len(gaps):
        finding(ctx, "lint", "checkbox-headings", "major",
                "%d cited claim blocks against %d GAP markers; this is a request for information, "
                "not a document" % (covered, len(gaps)), path=doc["path"], ident=doc["id"])
    for line, text in ctx["gap_errors"].get(doc["path"]) or []:
        finding(ctx, "lint", "gap-form", "major", text, path=doc["path"], ident=doc["id"],
                line=line)
    for match in CITE_LINE.finditer(doc["text"]):
        line = doc["text"].count("\n", 0, match.start()) + 1
        finding(ctx, "lint", "line-number-citation", "major",
                "citation %s uses a bare line number; cite a symbol or a verbatim anchor"
                % match.group(0), path=doc["path"], ident=doc["id"], line=line)
        break
    for line, target in relative_links(ctx["root"], doc["path"], doc["text"]):
        finding(ctx, "lint", "broken-link", "minor", "relative link does not resolve: %s" % target,
                path=doc["path"], ident=doc["id"], line=line)
    for match in REF_VERIFIED.finditer(doc["text"]):
        verified = parse_date(match.group(1))
        if verified is None:
            continue
        age = (ctx["today"] - verified).days
        if age > REF_AGE_DAYS:
            finding(ctx, "lint", "ref-age", "info",
                    "a ref: citation was verified %s, %d days ago" % (verified, age),
                    path=doc["path"], ident=doc["id"])
            break
    lint_citations(ctx, doc)
    lint_control(ctx, doc)


def anchor_resolves(text, names, anchor):
    if anchor in names:
        return True
    tail = anchor.split(".")[-1].split("::")[-1]
    if tail in names:
        return True
    for candidate in (anchor, tail):
        if re.search(r"(?<![\w.])%s(?![\w])" % re.escape(candidate), text):
            return True
    return False


def heading_slugs(text):
    slugs = set()
    for line in text.splitlines():
        match = HEADING.match(line.strip())
        if not match:
            continue
        slug = SLUG_CHARS.sub("-", match.group(1).strip().lower()).strip("-")
        if slug:
            slugs.add(slug)
    return slugs


def code_target(match):
    target = match.group(1).strip()
    anchor = (match.group(2) or "").strip()
    rel = target.split("#", 1)[0]
    if "#" in target:
        anchor = target.split("#", 1)[1]
    return rel, anchor


def code_file(ctx, rel):
    full = os.path.join(ctx["root"], rel)
    return inside_repo(ctx["root"], full) and safe_is_file(
        ctx["root"], repository_path(ctx["root"], full) or full)


def code_problem(ctx, rel, anchor):
    cache = ctx["cite_cache"]
    full = os.path.join(ctx["root"], rel)
    if not inside_repo(ctx["root"], full):
        # Containment, before anything opens the file. os.path.join with an absolute path or a
        # path carrying .. lands wherever the citation asks, so without this a citation resolved
        # against a file outside the repository and bound its numbers into this document.
        return outside_repo(rel)
    if not safe_is_file(ctx["root"], repository_path(ctx["root"], full) or full):
        return "stale-evidence", "citation names %s, which is not a file in this repository" % rel
    if rel not in cache:
        text = read_text(ctx["root"], full) or ""
        cache[rel] = (text, set(extract_declarations(rel, text)))
    text, names = cache[rel]
    if not anchor_resolves(text, names, anchor):
        return ("stale-evidence",
                "citation %s does not resolve in %s; a person decides whether the claim or the "
                "code moved" % (anchor, rel))
    return None


def ref_target(payload):
    parts = [part.strip() for part in payload.split(",")]
    target = parts[0]
    rel = target.split("#", 1)[0].strip()
    anchor = target.split("#", 1)[1].strip() if "#" in target else ""
    return rel, anchor


def ref_file(ctx, doc, rel):
    # Both readings, like docdna_backfill.py resolve_ref, and before the file is opened. The
    # lexical test alone let a symlink standing inside the repository and pointing out of it
    # resolve, so the file the ref actually read was one no author of this project controls.
    # Returns the resolved path, or None with the escape flag set when a candidate exists on disk
    # and leaves the tree, so the caller can name the refusal rather than call the file missing.
    root = os.path.normpath(ctx["root"])
    candidates = [os.path.join(root, rel), os.path.join(root, os.path.dirname(doc["path"]), rel)]
    escaped = False
    for candidate in candidates:
        full = os.path.normpath(candidate)
        if not os.path.lexists(full):
            continue
        if not inside_repo(root, full):
            escaped = True
            continue
        if not safe_is_file(root, repository_path(root, full) or full):
            continue
        return full, False
    return None, escaped


def ref_problem(ctx, doc, payload):
    rel, anchor = ref_target(payload)
    if not rel:
        return "stale-evidence", "ref: citation names no reference file: %s" % payload.strip()[:60]
    if "://" in rel:
        return ("stale-evidence",
                "ref: citation names %s, a URL; a ref names a reference file this repository "
                "carries, which is what makes it re-checkable" % rel)
    full, escaped = ref_file(ctx, doc, rel)
    if escaped:
        kind, detail = outside_repo(rel)
        return kind, "ref: %s" % detail
    if full is None:
        return ("stale-evidence",
                "ref: citation names %s, which is not a file in this repository" % rel)
    if not anchor:
        return None
    cache = ctx["ref_cache"]
    if full not in cache:
        text = read_text(ctx["root"], full) or ""
        cache[full] = (text, set(extract_declarations(rel, text)) | heading_slugs(text))
    text, names = cache[full]
    if not anchor_resolves(text, names, anchor):
        return ("stale-evidence",
                "ref: anchor %s does not occur in %s; a person decides whether the claim or the "
                "reference moved" % (anchor, rel))
    return None


def human_problem(payload):
    match = HUMAN_FORM.match(payload.strip())
    if match is None:
        return ("human: citation [human: %s] carries no handle and ISO date; the form is "
                "[human: @handle YYYY-MM-DD], because an unattributed statement is a "
                "recollection" % payload.strip()[:40])
    if parse_date(match.group(2)) is None:
        return "human: citation is dated %s, which is not a real date" % match.group(2)
    return None


def lint_citations(ctx, doc):
    for match in CITE_PARTS.finditer(doc["text"]):
        rel, anchor = code_target(match)
        if not anchor or "/" not in rel and "." not in rel:
            continue
        problem = code_problem(ctx, rel, anchor)
        if problem is not None:
            kind, detail = problem
            finding(ctx, "lint", kind, CITE_SEVERITY.get(kind, "major"), detail, path=doc["path"],
                    ident=doc["id"], line=doc["text"].count("\n", 0, match.start()) + 1)
    for match in CITE_REF_PARTS.finditer(doc["text"]):
        problem = ref_problem(ctx, doc, match.group(1))
        if problem is not None:
            kind, detail = problem
            finding(ctx, "lint", kind, CITE_SEVERITY.get(kind, "major"), detail, path=doc["path"],
                    ident=doc["id"], line=doc["text"].count("\n", 0, match.start()) + 1)
    for match in CITE_HUMAN_PARTS.finditer(doc["text"]):
        problem = human_problem(match.group(1))
        if problem is not None:
            finding(ctx, "lint", "human-citation", "major", problem, path=doc["path"],
                    ident=doc["id"], line=doc["text"].count("\n", 0, match.start()) + 1)


def binding_spans(text, anchor):
    # anchor_resolves accepts the tail of a dotted or scoped name, so the window has to be drawn
    # around whichever of the two actually occurs. Otherwise a citation that resolves by its tail
    # would bind nothing and every number beside it would be reported as fabricated.
    spans = anchor_spans(text, anchor)
    if spans:
        return spans
    tail = anchor.split(".")[-1].split("::")[-1]
    return anchor_spans(text, tail) if tail and tail != anchor else []


def code_backing(ctx, rel, anchor):
    # No anchor is no place, and the proximity rule needs a place to be near. Such a citation
    # resolves and it binds no number, which is what docdna_backfill.py resolve_code does with a
    # link citation.
    if not anchor:
        return ""
    entry = ctx["cite_cache"].get(rel)
    text = entry[0] if entry else ""
    return window_around(text, binding_spans(text, anchor))


def ref_backing(ctx, doc, payload):
    rel, anchor = ref_target(payload)
    if not anchor:
        return ""
    full, _ = ref_file(ctx, doc, rel)
    if full is None:
        return ""
    if full not in ctx["ref_cache"]:
        text = read_text(ctx["root"], full) or ""
        ctx["ref_cache"][full] = (text, set(extract_declarations(rel, text)) | heading_slugs(text))
    text = ctx["ref_cache"][full][0]
    spans = binding_spans(text, anchor.lstrip("#"))
    if not spans:
        for match in HEADING.finditer(text):
            if SLUG_CHARS.sub("-", match.group(1).strip().lower()).strip("-") == anchor.lstrip("#"):
                spans.append(match.span())
    return window_around(text, spans[:MAX_SPANS])


def claim_support(ctx, doc, text):
    # What the citations on this block actually buy. A citation that resolves buys the numbers
    # written within BIND_LINES lines of the place it names, and nothing else. A run citation buys
    # nothing at all: docdna never ran the command, so the output beside it is the writer quoting
    # themselves, and counting it as support was the author certifying their own figure. A human
    # citation is a person putting their handle on the number, which is the one way a number enters
    # uncited, and it is recorded rather than passed over in silence.
    support = []
    attested = []
    ran = []
    for match in CITE_RUN_PARTS.finditer(text):
        ran.append(match.group(1).strip())
    for match in CITE_PARTS.finditer(text):
        rel, anchor = code_target(match)
        if "/" not in rel and "." not in rel:
            continue
        if not inside_repo(ctx["root"], os.path.join(ctx["root"], rel)):
            # Containment before the file is opened, on the binding side as well as the lint side.
            # The lint pass reports the escape; here it buys nothing, because a file outside the
            # repository under analysis is not evidence about this repository.
            continue
        if anchor and code_problem(ctx, rel, anchor) is not None:
            continue
        if not anchor and not code_file(ctx, rel):
            continue
        if rel not in ctx["cite_cache"]:
            body = read_text(ctx["root"], rel) or ""
            ctx["cite_cache"][rel] = (body, set(extract_declarations(rel, body)))
        backing = code_backing(ctx, rel, anchor)
        if backing:
            support.append("%s\n%s" % (rel, backing))
    for match in CITE_REF_PARTS.finditer(text):
        if ref_problem(ctx, doc, match.group(1)) is not None:
            continue
        backing = ref_backing(ctx, doc, match.group(1))
        if backing:
            support.append(backing)
    for match in CITE_HUMAN_PARTS.finditer(text):
        if human_problem(match.group(1)) is None:
            attested.append(match.group(1).strip())
    return support, attested, ran


def block_support(ctx, doc, blocks):
    # claim_support for every block once, index for index, shared by the number rule and the
    # attestation report so neither resolves the same citations a second time.
    return [claim_support(ctx, doc, block["text"]) for block in blocks]


def sentence_start(text, position):
    # Where the sentence holding this position begins. A terminator inside 99.9 is not one, which
    # is why the pattern wants whitespace after it.
    start = 0
    for match in NUMBER_SENTENCE.finditer(text[:position]):
        start = match.end()
    return start


def negated(text, start):
    # A refusal reads to a bag of words exactly like the commitment it refuses. The cue has to sit
    # in the same sentence and within a few words of the term, or "no document states this. The RTO
    # is 4 hours." would silence the sentence that follows the refusal.
    lead = text[sentence_start(text, start):start]
    words = lead.split()
    return NUMBER_NEGATION.search(" ".join(words[-NUMBER_NEGATION_REACH:])) is not None


def illustrations(text):
    # Only when the quoted sentence is set inside prose of its own. A block that is nothing but a
    # quoted sentence is a claim in quotation marks, and quoting yourself is not a citation.
    spans = [match.span() for match in NUMBER_ILLUSTRATION.finditer(text)]
    if not spans:
        return []
    outside = []
    last = 0
    for start, end in spans:
        outside.append(text[last:start])
        last = end
    outside.append(text[last:])
    return spans if "".join(outside).strip() else []


def inside(spans, start, end):
    return any(low <= start and end <= high for low, high in spans)


def commitment_values(text):
    values = []
    taken = set()
    for label, pattern in NUMBER_VALUES:
        for match in pattern.finditer(text):
            if match.start() in taken:
                continue
            if NUMBER_STRUCTURAL.search(text[:match.start()]):
                continue
            if NUMBER_COUNTED.match(text[match.end():]):
                continue
            taken.add(match.start())
            values.append((label, match.start(), match.end()))
            if len(values) >= NUMBER_MAX_VALUES:
                return values
    return values


def associated(text, first, second, cells):
    # Proximity and grammar, not co-occurrence. The span between the term and the value has to be
    # connective and nothing else, so "the RTO is 4 hours" binds and "the RTO is named in section
    # 4 of the handbook" does not. A cell wall counts as a connective inside a table row and
    # nowhere else: "| Retention | 2555 days |" is a label beside its value, and the same pipes
    # inside a paragraph are somebody quoting a table.
    gap = text[first:second]
    if len(gap) > NUMBER_JOIN_CHARS:
        return False
    pattern = NUMBER_JOIN_CELL if cells else NUMBER_JOIN
    match = pattern.match(gap)
    return match is not None and match.end() == len(gap)


def commitment_number(text, cells=False):
    # A commitment is a term and the value it claims, joined. Matching the two anywhere in the same
    # block was the bug: it read "there are 3 configuration files, and none of them sets an SLA" as
    # an SLA of 3, and a checker that accuses correct prose is turned off before it catches
    # anything.
    values = commitment_values(text)
    if not values:
        return None
    shown = illustrations(text)
    for term in list(NUMBER_TERMS.finditer(text))[:NUMBER_MAX_TERMS]:
        if negated(text, term.start()):
            continue
        for label, start, end in values:
            if start >= term.end():
                if not associated(text, term.end(), start, cells):
                    continue
            elif not associated(text, end, term.start(), cells):
                continue
            low, high = min(term.start(), start), max(term.end(), end)
            if inside(shown, low, high):
                continue
            if negated(text, min(term.start(), start)):
                continue
            return "%s stated as %s (%s)" % (term.group(0), label,
                                             " ".join(text[start:end].split()))
    return None


def number_detail(what, loose, support, adopted, text):
    if support:
        where = ("%s, and %s appears in none of the sources this block cites within %d lines of "
                 "the symbol or anchor named"
                 % (what, ", ".join(loose[:4]), BIND_LINES))
    else:
        where = "%s sits in a claim block with no citation that binds a number" % what
    note = NUMBER_NOTE if adopted else "%s; %s" % (NUMBER_NOTE, NON_ADOPTED_NOTE)
    return "%s; %s: %s" % (where, note, clip(text, 70))


def provenance_detail(what, loose, region, text):
    return ("%s, and %s is not a value docdna derived for this document. A banner and a document "
            "control table are docdna's own provenance, so every number in one comes from the "
            "catalog entry, the frontmatter, the GAP count, or the stamp of this run; a number "
            "parked in the %s block answers to that and not to a citation: %s"
            % (what, ", ".join(loose[:4]), region, clip(text, 70)))


def provenance_support(ctx, doc):
    # docdna_claims.provenance_support: what docdna itself derived for this document, the same
    # values docdna_backfill.py --verify holds the banner and the document control block to.
    gaps = len(ctx["gaps_by_path"].get(doc["path"]) or [])
    return derived_provenance(doc["data"], ctx["catalog"].get(doc["id"]), gaps,
                              str(ctx["today"]), VERSION, SCHEMA)


def lint_attestations(ctx, doc, blocks, supports, adopted=True):
    # A run citation and a human citation are both a person vouching for a number. Neither is
    # verification, and check used to pass over both without a word, so a document built entirely
    # out of them read exactly like a document cited to the repository.
    severity = "major" if adopted else "minor"
    counts = {"run": 0, "attested": 0}
    for block, (_, attested, ran) in zip(blocks, supports):
        if block["region"] in PROVENANCE_REGIONS:
            continue
        for command in ran:
            counts["run"] += 1
            finding(ctx, "lint", "run-self-attested", severity,
                    "the run citation `%s` is SELF-ATTESTED, NOT VERIFIED: %s: %s"
                    % (clip(command, 60), RUN_NOTE, clip(block["text"], 70)),
                    path=doc["path"], ident=doc["id"], line=block["line"])
        for who in attested:
            counts["attested"] += 1
            finding(ctx, "lint", "human-attested", "minor",
                    "this claim block rests on the attestation of %s and on nothing in the "
                    "repository; %s: %s" % (who, HUMAN_NOTE, clip(block["text"], 70)),
                    path=doc["path"], ident=doc["id"], line=block["line"])
    return counts


def lint_numbers(ctx, doc, blocks, supports, adopted=True):
    # Every block. Region decides what supports a block, never whether it is read.
    severity = "major" if adopted else "minor"
    provenance = provenance_support(ctx, doc)
    flagged = 0
    for block, (support, attested, _) in zip(blocks, supports):
        prose = strip_citations(block["text"])
        what = commitment_number(prose, block["kind"] in CELL_KINDS)
        if what is None:
            continue
        own = block["region"] in PROVENANCE_REGIONS
        if own:
            support = support + [provenance]
        elif attested:
            # lint_attestations already reported the block as attested rather than verified.
            continue
        loose = unsupported_numbers(prose, support)
        if not loose:
            continue
        flagged += 1
        if own:
            finding(ctx, "lint", "provenance-number", severity,
                    provenance_detail(what, loose, block["region"], block["text"]),
                    path=doc["path"], ident=doc["id"], line=block["line"])
            continue
        finding(ctx, "lint", "generated-number", severity,
                number_detail(what, loose, support, adopted, block["text"]),
                path=doc["path"], ident=doc["id"], line=block["line"])
    return flagged


def lint_control(ctx, doc):
    values = control_values(doc["lines"][doc["body_start"]:])
    if not values:
        return
    data = doc["data"]
    pairs = [("status", "status"), ("owner", "owner"), ("last reviewed", "last_reviewed")]
    for label, key in pairs:
        shown = values.get(label)
        recorded = data.get(key)
        if shown is None or recorded in (None, []):
            continue
        if not str(shown).startswith(str(recorded)):
            finding(ctx, "lint", "control-mismatch", "major",
                    "document control says %s: %s and the frontmatter says %s"
                    % (label, shown, recorded), path=doc["path"], ident=doc["id"])


def lint_prose(ctx):
    # The number rule, and only the number rule, on documents docdna never wrote. Frontmatter,
    # covers and citation coverage are contracts a hand-written document never signed, so none of
    # them are checked here. An unsourced availability target is a claim about the world either
    # way, and it is the one thing a reader cannot tell apart from a derived one.
    for doc in ctx["prose"]:
        blocks = document_blocks(doc)
        supports = block_support(ctx, doc, blocks)
        doc["claims"] = {"blocks": len(blocks),
                         "numbers": lint_numbers(ctx, doc, blocks, supports, False)}
        doc["claims"].update(lint_attestations(ctx, doc, blocks, supports, False))


def pass_lint(ctx):
    for doc in ctx["documents"]:
        if doc["error"] is not None:
            finding(ctx, "lint", "frontmatter-unparsable", "blocker",
                    "frontmatter is not readable by the restricted parser: %s. It is rejected, "
                    "never guessed at." % doc["error"], path=doc["path"], ident=doc["id"])
            continue
        lint_keys(ctx, doc)
        lint_enums(ctx, doc)
        lint_covers(ctx, doc)
        lint_body(ctx, doc)
    lint_prose(ctx)
    lint_sidecars(ctx)
    seen = {}
    for doc in ctx["documents"]:
        key = (doc["id"], doc["data"].get("instance_id"))
        if doc["id"] is None:
            continue
        if key in seen:
            finding(ctx, "lint", "duplicate-id", "major",
                    "id %s with instance_id %s is claimed by %s as well"
                    % (key[0], key[1], seen[key]), path=doc["path"], ident=doc["id"])
        seen[key] = doc["path"]
    for ident in ctx["config"]["assurance_set"]:
        if ctx["catalog"] and ident not in ctx["catalog"]:
            finding(ctx, "lint", "assurance-set-id", "minor",
                    "assurance_set names %s, which is not in catalog/documents.json" % ident)


def collect_gaps(ctx):
    for doc in ctx["documents"]:
        if doc["kind"] != "markdown":
            continue
        records, errors = gap_records(doc["text"], doc["path"])
        for record in records:
            record["document"] = doc["id"] or doc["path"]
            ctx["gaps"].append(record)
        ctx["gaps_by_path"][doc["path"]] = records
        ctx["gap_errors"][doc["path"]] = errors
    for doc in ctx["prose"]:
        # The markers are counted, because the count is one of the values a banner or a document
        # control block may state. They do not enter the gap register: a document nobody adopted
        # has no owner to route the question to, and inventing one would be the register lying.
        # Neither do they shield anything, since citation coverage is never asked of prose.
        records, _ = gap_records(doc["text"], doc["path"])
        ctx["gaps_by_path"][doc["path"]] = records


def pass_gaps(ctx):
    by_severity = Counter()
    by_owner = Counter()
    by_document = Counter()
    by_kind = Counter()
    for record in ctx["gaps"]:
        by_severity[record["sev"] or "unset"] += 1
        by_owner[record["owner"] or "unassigned"] += 1
        by_document[record["document"]] += 1
        by_kind[record["kind"] or "unset"] += 1
    items = sorted(ctx["gaps"], key=lambda row: (SEVERITY_RANK.get(row["sev"], 0) * -1,
                                                 row["path"], row["line"]))
    unassigned = by_owner.get("unassigned", 0)
    ctx["report"]["gaps"] = {"total": len(ctx["gaps"]), "by_severity": dict(by_severity),
                             "by_owner": dict(by_owner), "by_document": dict(by_document),
                             "by_kind": dict(by_kind), "unassigned": unassigned,
                             "owner_note": OWNER_NOTE, "items": items, "written": False}
    for record in items:
        finding(ctx, "gaps", "open-gap", "info",
                "%s (%s): %s" % (record["id"], record["sev"], record["asks"] or "no asks recorded"),
                path=record["path"], ident=record["document"], line=record["line"])
    if ctx["write"]:
        ctx["report"]["gaps"]["written"] = write_gaps_block(ctx)


def gaps_block(ctx):
    rollup = ctx["report"]["gaps"]
    lines = [GAPS_START, "## Open gaps", ""]
    if not rollup["total"]:
        lines.append("No open GAP markers in the documents docdna has adopted.")
    else:
        counts = ", ".join("%d %s" % (rollup["by_severity"][key], key)
                           for key in sorted(rollup["by_severity"],
                                             key=lambda item: -SEVERITY_RANK.get(item, 0)))
        lines.append("%d open %s: %s." % (rollup["total"],
                                          "gap" if rollup["total"] == 1 else "gaps", counts))
        if rollup["unassigned"]:
            lines.append("")
            lines.append("Owner unassigned on %d of %d. %s."
                         % (rollup["unassigned"], rollup["total"], OWNER_NOTE))
        lines.append("")
        lines.append("| Gap | Severity | Kind | Owner | Document | Asks |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for record in rollup["items"]:
            lines.append("| %s | %s | %s | %s | %s | %s |"
                         % (record["id"], record["sev"] or "unset", record["kind"] or "unset",
                            record["owner"], record["document"],
                            (record["asks"] or "").replace("|", "/")))
    lines.append("")
    lines.append("Regenerated by %s %s on %s." % (TOOL, VERSION, ctx["today"]))
    lines.append(GAPS_END)
    return "\n".join(lines) + "\n"


def write_gaps_block(ctx):
    if not safe_path_exists(ctx["root"], REPORT_REL):
        return False
    text = read_text(ctx["root"], REPORT_REL)
    if text is None:
        return False
    start = text.find(GAPS_START)
    end = text.find(GAPS_END, start) if start != -1 else -1
    if start != -1 and end == -1:
        # The block was opened and never closed, so there is no telling where it ends. Appending a
        # second block here made the next run treat everything between the two opening markers as
        # the old block and delete it, which is a person's text gone without a word.
        finding(ctx, "gaps", "gaps-block-unterminated", "major",
                "%s opens a gaps block with %s and never closes it with %s, so the open gaps were "
                "not written; close or remove the marker by hand" % (REPORT_REL, GAPS_START,
                                                                     GAPS_END),
                path=REPORT_REL, line=text.count("\n", 0, start) + 1)
        return False
    if not ctx["report"]["gaps"]["total"] and start == -1:
        return False
    block = gaps_block(ctx)
    if start != -1:
        end += len(GAPS_END)
        head = text[:start].rstrip()
        joiner = "\n\n" if head else ""
        updated = head + joiner + block.rstrip() + "\n" + text[end:].lstrip()
        updated = updated.rstrip() + "\n"
    elif text.strip():
        updated = text.rstrip() + "\n\n" + block
    else:
        updated = block
    clean_report, _stats = clean_generated_text(updated)
    safe_write_text(ctx["root"], REPORT_REL, clean_report)
    return True


def node_class(ident):
    for prefix in ("bc-", "prd-", "req-", "adr-", "tc-", "pm-", "inc-", "rsk-", "ctl-", "thr-",
                   "waiver-", "abuse-case-"):
        if ident.startswith(prefix):
            return prefix.rstrip("-")
    if ":" in ident:
        return ident.split(":", 1)[0]
    return "doc"


def spine_of(ident):
    node = node_class(ident)
    if node in ("rsk", "ctl", "evidence", "assessment", "waiver"):
        return "assurance"
    if node in ("thr", "abuse-case", "mitigation"):
        return "abuse"
    return "delivery"


def node_exists(ctx, ident):
    if ident in ctx["spine_nodes"]:
        return True
    for prefix in PATH_PREFIXES:
        if ident.startswith(prefix):
            payload = ident[len(prefix):].split("::", 1)[0].split("@", 1)[-1]
            return safe_path_exists(ctx["root"], payload)
    return ident.startswith(EXTERNAL_PREFIXES)


def add_edge(graph, parent, child):
    graph.setdefault(parent, [])
    graph.setdefault(child, [])
    if child not in graph[parent]:
        graph[parent].append(child)


def descendants(graph, start):
    seen = set()
    queue = list(graph.get(start) or [])
    while queue:
        node = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        queue.extend(graph.get(node) or [])
    return seen


def ancestors(graph, start):
    reverse = {}
    for parent, children in graph.items():
        for child in children:
            reverse.setdefault(child, []).append(parent)
    seen = set()
    queue = list(reverse.get(start) or [])
    while queue:
        node = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        queue.extend(reverse.get(node) or [])
    return seen


def build_spine(ctx):
    graph = {}
    nodes = set()
    for doc in ctx["documents"]:
        data = doc["data"]
        ident = data.get("instance_id") or doc["id"]
        if not ident:
            continue
        nodes.add(ident)
        graph.setdefault(ident, [])
    ctx["spine_nodes"] = nodes
    for doc in ctx["documents"]:
        data = doc["data"]
        ident = data.get("instance_id") or doc["id"]
        if not ident:
            continue
        for parent in as_list(data.get("traces_up")):
            add_edge(graph, str(parent), ident)
        for child in as_list(data.get("traces_down")):
            add_edge(graph, ident, str(child))
    for row in ctx["annotations"]:
        target = row["target"]
        node = ("test:" if is_test_path(row["path"]) else "module:") + row["path"]
        nodes.add(node)
        nodes.add(target)
        add_edge(graph, target, node)
    ctx["spine_nodes"] = nodes
    return graph


def is_test_path(rel):
    lower = rel.lower()
    base = os.path.basename(lower)
    return ("test" in base or "spec" in base or "/tests/" in "/" + lower
            or "/spec/" in "/" + lower)


def spine_coverage(ctx, graph):
    rows = []
    for name, source, target in SPINE_SPECS:
        method = "annotation"
        parents = sorted(node for node in graph if node_class(node) == source)
        if not ctx["annotations"]:
            rows.append({"spine": name, "from": source, "to": target, "method": method,
                         "coverage": None, "reason": NO_ANNOTATIONS, "nodes": len(parents),
                         "covered": 0})
            continue
        wanted = DESCENDANTS.get(source) or ()
        covered = 0
        for node in parents:
            reached = descendants(graph, node)
            if any(item.startswith(wanted) for item in reached):
                covered += 1
        if not parents:
            rows.append({"spine": name, "from": source, "to": target, "method": method,
                         "coverage": None, "reason": "no %s- nodes are declared" % source,
                         "nodes": 0, "covered": 0})
            continue
        rows.append({"spine": name, "from": source, "to": target, "method": method,
                     "coverage": round(float(covered) / len(parents), 2), "reason": None,
                     "nodes": len(parents), "covered": covered})
    return rows


def pass_spine(ctx):
    graph = build_spine(ctx)
    for doc in ctx["documents"]:
        data = doc["data"]
        for key in ("traces_up", "traces_down"):
            for token in as_list(data.get(key)):
                token = str(token)
                if not node_exists(ctx, token):
                    finding(ctx, "spine", "unresolved-trace", "major",
                            "%s names %s, which resolves to nothing in this repository"
                            % (key, token), path=doc["path"], ident=doc["id"])
    for node in sorted(graph):
        klass = node_class(node)
        wanted = DESCENDANTS.get(klass)
        if wanted:
            reached = descendants(graph, node)
            if not any(item.startswith(wanted) for item in reached):
                severity = spine_severity(ctx, klass)
                finding(ctx, "spine", "no-" + wanted[0].strip(":-") + "-descendant", severity,
                        "%s has no %s descendant" % (node, " or ".join(wanted)), ident=None)
        if klass == "module" and not any(node_class(item) == "req"
                                         for item in ancestors(graph, node)):
            finding(ctx, "spine", "module-without-requirement", "info",
                    "%s has no req- ancestor" % node)
    counts = Counter(spine_of(node) for node in graph)
    ctx["report"]["spine"] = {"graphs": {name: counts.get(name, 0)
                                         for name in ("delivery", "assurance", "abuse")},
                              "nodes": len(graph), "edges": sum(len(v) for v in graph.values()),
                              "annotations": len(ctx["annotations"]),
                              "coverage": spine_coverage(ctx, graph)}


def spine_severity(ctx, klass):
    if klass == "req":
        return "major" if ctx["config"]["regulated"] else "minor"
    if klass == "thr":
        return "major" if ctx["config"]["safety_critical"] else "minor"
    return "minor"


def pass_tripwires(ctx):
    manifest = ctx["manifest"]
    rows = []
    if manifest is None:
        ctx["report"]["tripwires"] = {"firing": [], "checked": 0,
                                      "note": "no .docdna/manifest.json; run docdna_select.py "
                                              "before tripwires mean anything"}
        return
    engine = {"signals": ctx["signals"], "answers": ctx["answers"],
              "archetype": (manifest.get("archetype") or {}).get("primary", "unknown"),
              "overlays": (manifest.get("archetype") or {}).get("overlays") or [],
              "docstate": ctx["docstate"]}
    checked = 0
    for row in manifest.get("excluded") or []:
        node = row.get("revisit_when")
        if not node:
            continue
        checked += 1
        try:
            fired = predicate(engine, node)
        except ValueError as error:
            finding(ctx, "tripwires", "unevaluable", "minor",
                    "%s: %s" % (row.get("id"), error), ident=row.get("id"))
            continue
        if not fired:
            continue
        terms = []
        try:
            true_terms(engine, node, terms)
        except ValueError:
            terms = []
        entry = {"id": row.get("id"), "title": row.get("title"), "rule": row.get("rule"),
                 "because": row.get("because"), "terms": terms,
                 "evidence": term_evidence(engine, terms)}
        rows.append(entry)
        detail = "%s was excluded because %s; %s now fires" % (row.get("id"), row.get("because"),
                                                               ", ".join(terms) or "its predicate")
        finding(ctx, "tripwires", "tripwire", "major", detail, ident=row.get("id"))
    rows.sort(key=lambda item: item["id"] or "")
    ctx["report"]["tripwires"] = {"firing": rows, "checked": checked, "note": None}


def pass_orphans(ctx):
    manifest = ctx["manifest"]
    rows = []
    if manifest is None:
        ctx["report"]["orphans"] = {"items": [],
                                    "note": "no .docdna/manifest.json; nothing defines what this "
                                            "repository owes, so orphans cannot be named"}
        return
    excluded = {}
    for row in manifest.get("excluded") or []:
        excluded[row.get("id")] = row
    verdicts = {}
    for row in manifest.get("documents") or []:
        verdicts[row.get("id")] = row
    for doc in ctx["documents"]:
        ident = doc["id"]
        if not ident:
            continue
        where = ctx["found_paths"].get(ident) or doc["path"]
        if ctx["catalog"] and ident not in ctx["catalog"]:
            rows.append({"path": doc["path"], "id": ident, "kind": "unknown-id",
                         "because": "no catalog entry carries this id"})
            continue
        if ident in excluded:
            rows.append({"path": where, "id": ident, "kind": "excluded",
                         "because": excluded[ident].get("because")})
            continue
        row = verdicts.get(ident)
        if row is not None and row.get("verdict") == "not-applicable":
            rows.append({"path": where, "id": ident, "kind": "not-applicable",
                         "because": (row.get("because") or ["the profile marks it "
                                                            "not-applicable"])[0]})
    for row in manifest.get("documents") or []:
        if row.get("verdict") != "not-applicable" or not row.get("found_at"):
            continue
        if any(item["id"] == row.get("id") for item in rows):
            continue
        rows.append({"path": row["found_at"], "id": row.get("id"), "kind": "not-applicable",
                     "because": (row.get("because") or ["the profile marks it not-applicable"])[0]})
    for row in rows:
        finding(ctx, "orphans", row["kind"], "info",
                "%s exists and nothing in the profile justifies it: %s"
                % (row["path"], row["because"]), path=row["path"], ident=row["id"])
    ctx["report"]["orphans"] = {"items": rows, "note": None}


def pass_hygiene(ctx):
    records = []
    seen = set()
    for doc in ctx["documents"] + ctx["prose"]:
        if doc["path"] in seen:
            continue
        seen.add(doc["path"])
        records.append(doc)
    for row in ctx["scan"]["inventory"]["docs"]:
        rel = row["path"]
        if rel in seen or not rel.lower().endswith(TEXT_DOC_EXT):
            continue
        if row.get("bytes") is None:
            continue
        text = read_text(ctx["root"], rel)
        if text is None:
            continue
        seen.add(rel)
        records.append({"path": rel, "id": ctx["path_ids"].get(rel), "text": text})
    counts = Counter()
    total = 0
    major_details = []
    minor_details = []
    sequence = 0
    for doc in records:
        for hit in inspect_unicode(doc["text"]):
            counts[hit["kind"]] += 1
            total += 1
            sequence += 1
            bucket = major_details if hit["severity"] == "major" else minor_details
            if len(bucket) >= MAX_HYGIENE_FINDINGS:
                continue
            detail = ("column %d contains %s %s (%s); deterministic Unicode hygiene can %s "
                      "it, but check never rewrites user-authored documentation"
                      % (hit["column"], hit["codepoint"], hit["name"], hit["kind"],
                         hit["action"]))
            row = {"sequence": sequence - 1, "kind": "unicode-" + hit["kind"],
                   "severity": hit["severity"], "detail": detail, "path": doc["path"],
                   "id": doc.get("id"), "line": hit["line"], "column": hit["column"]}
            bucket.append(row)
    detail_rows = major_details[:MAX_HYGIENE_FINDINGS]
    detail_rows.extend(minor_details[:MAX_HYGIENE_FINDINGS - len(detail_rows)])
    detail_rows.sort(key=lambda row: row["sequence"])
    for row in detail_rows:
        finding(ctx, "hygiene", row["kind"], row["severity"], row["detail"],
                path=row["path"], ident=row["id"], line=row["line"], column=row["column"])
    emitted = len(detail_rows)
    ctx["report"]["hygiene"] = {
        "inspected": len(records),
        "findings": total,
        "emitted": emitted,
        "omitted": total - emitted,
        "by_kind": dict(sorted(counts.items())),
        "boundary": ("deterministic inspection covers invisible format characters and space "
                     "lookalikes; it does not detect statistical token-sampling watermarks, "
                     "prove human authorship, or inspect file-container metadata"),
        "writes": "check reports user-authored documents and never rewrites them",
    }


def pass_prose(ctx):
    records = []
    seen = set()
    for doc in ctx["documents"] + ctx["prose"]:
        if doc["path"] in seen or doc["kind"] not in ("markdown", "prose"):
            continue
        seen.add(doc["path"])
        records.append(doc)
    counts = Counter()
    total = 0
    emitted = 0
    for doc in records:
        for hit in inspect_prose(doc["text"], path=doc["path"]):
            counts[hit["kind"]] += 1
            total += 1
            if emitted >= MAX_PROSE_FINDINGS:
                continue
            detail = "%s; matched %r" % (hit["detail"], hit["match"])
            finding(ctx, "prose", hit["kind"], "minor", detail, path=doc["path"],
                    ident=doc.get("id"), line=hit["line"], column=hit["column"])
            emitted += 1
    ctx["report"]["prose_review"] = {
        "inspected": len(records),
        "findings": total,
        "emitted": emitted,
        "omitted": total - emitted,
        "by_kind": dict(sorted(counts.items())),
        "boundary": ("advisory literal-pattern review of rendered Markdown prose; it does not infer "
                     "authorship, judge factual support, or evaluate voice in context"),
        "ignored": ("frontmatter, fenced and inline code, literal examples, HTML comments, link "
                    "destinations, and autolinks"),
        "writes": "never",
        "gates": "never",
    }


def staleness_summary(ctx):
    counts = Counter()
    for record in (ctx["report"].get("drift") or {}).get("digest") or []:
        for key, value in record["staleness"].items():
            if value:
                counts[key] += 1
    return {"calendar_stale": counts["calendar_stale"], "drift_stale": counts["drift_stale"],
            "expiry_stale": counts["expiry_stale"], "unverifiable": counts["unverifiable"],
            "note": UNVERIFIABLE_NOTE}


def check(repo, passes, fail_on, scan_path, write, exclude_dirs=None):
    requested_root = os.path.abspath(repo)
    if not os.path.isdir(requested_root):
        raise ValueError("%s is not a directory" % repo)
    root = safe_bind_root(requested_root)
    try:
        return check_bound(root, passes, fail_on, scan_path, write, exclude_dirs)
    finally:
        root.close()


def check_bound(root, passes, fail_on, scan_path, write, exclude_dirs=None):
    excludes = list(exclude_dirs or []) + config_excludes(root)
    scan = (safe_parse_json(safe_read_bounded_path(scan_path, MAX_CONTROL_BYTES), scan_path)
            if scan_path else run_scan(root, excludes))
    safe_require_scan(scan, "scan", SCHEMA)
    scan_root = os.path.abspath(scan["root"])
    if os.path.realpath(scan_root) != os.path.realpath(root):
        raise ValueError("scan root %s does not match repository %s"
                         % (scan["root"], root))
    safe_require_root_identity(root, scan.get("root_identity"), "scan")
    if scan_path:
        current = run_scan(root, excludes)
        safe_require_scan(current, "current scan", SCHEMA)
        if scan.get("content_fingerprint") != current.get("content_fingerprint"):
            raise ValueError("imported scan does not match the current repository contents")
        current["generated"] = scan["generated"]
        scan = current
    manifest = load_manifest(root)
    catalog = load_catalog_documents()
    config = load_config(root, manifest)
    documents = collect_documents(root, scan)
    prose = collect_prose(root, scan, documents)
    answers = {}
    for key, row in ((manifest or {}).get("interview") or {}).items():
        answers[key] = row.get("value")
    docstate = {}
    found_paths = {}
    for row in (manifest or {}).get("documents") or []:
        docstate[row.get("id")] = row.get("state") or "absent"
        if row.get("found_at"):
            found_paths[row["id"]] = row["found_at"]
    path_ids = {}
    for doc in documents:
        if doc["id"]:
            path_ids[doc["path"]] = doc["id"]
    for ident, where in found_paths.items():
        path_ids.setdefault(where, ident)
    ctx = {"root": root, "scan": scan, "manifest": manifest, "catalog": catalog, "config": config,
           "documents": documents, "prose": prose, "signals": signal_map(scan), "answers": answers,
           "docstate": docstate, "found_paths": found_paths, "path_ids": path_ids,
           "sidecar_ids": set(doc["sidecar"] for doc in documents if doc["sidecar"]),
           "adopted": bool(documents) or safe_is_dir(root, META_REL),
           "annotations": [], "findings": [], "gaps": [], "gaps_by_path": {}, "gap_errors": {},
           "cite_cache": {}, "ref_cache": {},
           "today": today(), "write": write, "spine_nodes": set(), "report": {}}
    collect_gaps(ctx)
    if "spine" in passes:
        ctx["annotations"] = collect_annotations(root)
    if "drift" in passes:
        pass_drift(ctx)
    if "lint" in passes:
        pass_lint(ctx)
    if "prose" in passes:
        pass_prose(ctx)
    if "hygiene" in passes:
        pass_hygiene(ctx)
    if "gaps" in passes:
        pass_gaps(ctx)
    if "spine" in passes:
        pass_spine(ctx)
    if "tripwires" in passes:
        pass_tripwires(ctx)
    if "orphans" in passes:
        pass_orphans(ctx)
    threshold = GATE_RANK[fail_on]
    gating = [row for row in ctx["findings"]
              if row["gating"] and SEVERITY_RANK[row["severity"]] >= threshold]
    severities = Counter(row["severity"] for row in ctx["findings"])
    report = {"schema": SCHEMA, "tool": TOOL, "version": VERSION, "generated": now_utc(),
              "root": root, "commit": scan.get("commit"), "dirty": scan.get("dirty"),
              "passes": sorted(passes), "config": config,
              "manifest": {"present": manifest is not None,
                           "generated_at": (manifest or {}).get("generated_at"),
                           "documents": len((manifest or {}).get("documents") or []),
                           "excluded": len((manifest or {}).get("excluded") or [])},
              "documents": [document_row(doc) for doc in documents],
              "prose": [document_row(doc) for doc in prose],
              "numbers": numbers_report(ctx),
              "findings": ctx["findings"],
              "staleness": staleness_summary(ctx) if "drift" in passes else None,
              "summary": {"findings": len(ctx["findings"]), "gating": len(gating),
                          "fail_on": fail_on, "by_severity": dict(severities),
                          "exit": 1 if gating else 0}}
    for key in ("drift", "prose_review", "hygiene", "gaps", "spine", "tripwires", "orphans"):
        report[key] = ctx["report"].get(key)
    return report


def numbers_report(ctx):
    counts = Counter(row["kind"] for row in ctx["findings"])
    loose = set(doc["path"] for doc in ctx["prose"])
    return {"region": NUMBER_REGION, "shared_with": "docdna_backfill.py --verify",
            "difference": NUMBER_DIFFERENCE, "binding": NUMBER_BINDING, "misses": NUMBER_MISSES,
            "self_attested": RUN_NOTE, "linted": len(ctx["documents"]) + len(ctx["prose"]),
            "adopted": len(ctx["documents"]), "not_adopted": len(ctx["prose"]),
            "flagged": counts["generated-number"],
            "flagged_provenance": counts["provenance-number"],
            "flagged_run": counts["run-self-attested"],
            "flagged_attested": counts["human-attested"],
            "flagged_not_adopted": len([row for row in ctx["findings"]
                                        if row["kind"] == "generated-number"
                                        and row["path"] in loose])}


def document_row(doc):
    data = doc["data"] or {}
    return {"path": doc["path"], "id": doc["id"], "kind": doc["kind"],
            "status": data.get("status"), "owner": data.get("owner"),
            "stage": data.get("stage"), "derivation": data.get("derivation"),
            "covers": as_list(data.get("covers")), "claims": doc.get("claims"),
            "frontmatter_error": doc["error"]}


def clip(text, width):
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[:width - 3] + "..."


def plural(count, word):
    return "%d %s" % (count, word if count == 1 else word + "s")


def print_tripwires(report):
    rows = (report.get("tripwires") or {}).get("firing") or []
    if not rows:
        return
    print("\nTRIPWIRES FIRING (%d), documents excluded earlier that the code now requires"
          % len(rows))
    for row in rows:
        where = ", ".join(row["evidence"][:2])
        terms = ", ".join(row["terms"]) or "its revisit_when predicate"
        print("  %-9s: %s" % ("fires", clip(row["id"] + ": " + (row["title"] or ""), 88)))
        print("  %-9s: %s%s" % ("", clip("now true: " + terms, 80),
                                " (%s)" % where if where else ""))


def print_findings(report, pass_name, title, limit=12):
    rows = [row for row in report["findings"] if row["pass"] == pass_name
            and row["severity"] != "info"]
    if not rows:
        return
    print("\n%s (%d)" % (title, len(rows)))
    for row in rows[:limit]:
        where = row["path"] or row["id"] or "-"
        if row.get("line"):
            where = "%s:%d" % (where, row["line"])
        if row.get("column"):
            where = "%s:%d" % (where, row["column"])
        print("  %-9s: %s -> %s" % (row["severity"], clip(where, 34), clip(row["detail"], 60)))
    if len(rows) > limit:
        print("  %-9s: %d more" % ("...", len(rows) - limit))


def print_text(report):
    print("docdna check %s" % VERSION)
    print("  %-9s: %s" % ("root", report["root"]))
    head = (report["commit"] or "")[:12] or "no git history"
    print("  %-9s: %s%s" % ("commit", head, " (dirty)" if report["dirty"] else ""))
    manifest = report["manifest"]
    if manifest["present"]:
        print("  %-9s: %d documents, %d exclusions, generated %s"
              % ("manifest", manifest["documents"], manifest["excluded"],
                 manifest["generated_at"]))
    else:
        print("  %-9s: %s" % ("manifest", "absent; run docdna_select.py for tripwires and orphans"))
    print("  %-9s: %d with docdna frontmatter" % ("adopted", len(report["documents"])))
    numbers = report.get("numbers") or {}
    if numbers:
        print("  %-9s: %d documents linted for unsourced numbers, %d of them not adopted"
              % ("numbers", numbers["linted"], numbers["not_adopted"]))
        print("  %-9s: %s" % ("", clip(numbers["region"], 92)))
        print("  %-9s: %s" % ("", clip(numbers["binding"], 92)))
        print("  %-9s: %s" % ("", clip("differs from %s: %s"
                                       % (numbers["shared_with"], numbers["difference"]), 92)))
        if numbers["flagged_run"] or numbers["flagged_attested"]:
            print("  %-9s: %d run citation%s SELF-ATTESTED and never verified, %d claim block%s "
                  "resting on a human attestation"
                  % ("attested", numbers["flagged_run"],
                     "" if numbers["flagged_run"] == 1 else "s", numbers["flagged_attested"],
                     "" if numbers["flagged_attested"] == 1 else "s"))
            print("  %-9s: %s" % ("", clip(numbers["self_attested"], 92)))
    assurance = report["config"]["assurance_set"]
    print("  %-9s: fail-on %s; assurance_set %s"
          % ("gate", report["summary"]["fail_on"],
             ", ".join(assurance) if assurance else "empty, so drift only warns"))
    print_tripwires(report)
    print_findings(report, "drift", "drift, warning unless the document is in assurance_set")
    print_findings(report, "lint", "lint")
    prose_review = report.get("prose_review")
    if prose_review is not None:
        print("\nprose review, advisory and never gating")
        print("  %-9s: %d Markdown documents, %d findings" %
              ("checked", prose_review["inspected"], prose_review["findings"]))
        if prose_review["omitted"]:
            print("  %-9s: %d rows emitted, %d omitted from detail" %
                  ("bounded", prose_review["emitted"], prose_review["omitted"]))
        print("  %-9s: %s" % ("boundary", clip(prose_review["boundary"], 92)))
        print_findings(report, "prose", "prose review findings")
    hygiene = report.get("hygiene")
    if hygiene is not None:
        print("\nunicode hygiene, deterministic text inspection")
        print("  %-9s: %d documents, %d findings" %
              ("checked", hygiene["inspected"], hygiene["findings"]))
        if hygiene["omitted"]:
            print("  %-9s: %d rows emitted, %d omitted from detail" %
                  ("bounded", hygiene["emitted"], hygiene["omitted"]))
        print("  %-9s: %s" % ("boundary", clip(hygiene["boundary"], 92)))
        print_findings(report, "hygiene", "unicode hygiene findings")
    print_findings(report, "spine", "spine")
    gaps = report.get("gaps")
    if gaps is not None:
        counts = ", ".join("%d %s" % (gaps["by_severity"][key], key)
                           for key in sorted(gaps["by_severity"],
                                             key=lambda item: -SEVERITY_RANK.get(item, 0)))
        print("\ngaps (%d)" % gaps["total"])
        print("  %-9s: %s" % ("severity", counts or "none open"))
        print("  %-9s: %d unassigned; %s" % ("owner", gaps["unassigned"], OWNER_NOTE))
        if gaps["written"]:
            print("  %-9s: %s" % ("written", "## Open gaps regenerated in " + REPORT_REL))
        for row in report["findings"]:
            if row["kind"] == "gaps-block-unterminated":
                print("  %-9s: %s" % ("refused", clip(row["detail"], 92)))
    spine = report.get("spine")
    if spine is not None:
        print("\nspine, built from explicit annotations only")
        print("  %-9s: %s, %s, %s" % ("graph", plural(spine["nodes"], "node"),
                                      plural(spine["edges"], "edge"),
                                      plural(spine["annotations"], "@covers annotation")))
        for row in spine["coverage"]:
            value = "null (%s)" % row["reason"] if row["coverage"] is None else \
                "%.0f%% (%d of %d)" % (row["coverage"] * 100, row["covered"], row["nodes"])
            print("  %-9s: %s" % (row["spine"], value))
    orphans = report.get("orphans")
    if orphans is not None and orphans["items"]:
        print("\norphans (%d)" % len(orphans["items"]))
        for row in orphans["items"][:6]:
            print("  %-9s: %s (%s)" % (row["kind"][:9], row["path"], clip(row["because"], 50)))
    staleness = report.get("staleness")
    if staleness is not None:
        print("\nstaleness, four verdicts, never conflated")
        print("  %-9s: %d calendar, %d drift, %d expiry, %d unverifiable"
              % ("counts", staleness["calendar_stale"], staleness["drift_stale"],
                 staleness["expiry_stale"], staleness["unverifiable"]))
        print("  %-9s: %s" % ("note", UNVERIFIABLE_NOTE))
    summary = report["summary"]
    print("\n%-11s: %s, %d gating at or above %s"
          % ("exit %d" % summary["exit"], plural(summary["findings"], "finding"),
             summary["gating"], summary["fail_on"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check documentation against the code: drift, "
                                                 "lint, prose, Unicode hygiene, gaps, spine, "
                                                 "tripwires, orphans.")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--fail-on", choices=FAIL_ON, default="major",
                        help="exit 1 on a gated finding at this severity or above")
    parser.add_argument("--only", action="append", choices=PASSES,
                        help="run only this pass, repeatable")
    parser.add_argument("--scan", metavar="PATH",
                        help="validate scanner JSON, reproduce a fresh scan, and reject changed contents")
    parser.add_argument("--no-write", action="store_true",
                        help="never touch DOCDNA.md, even when the gaps pass runs")
    parser.add_argument("--exclude-dir", action="append", metavar="DIR",
                        help="keep a directory out of the document inventory, the drift pass, "
                             "and signal detection, for vendored or fixture repositories that "
                             "carry their own documentation and manifests, repeatable")
    args = parser.parse_args(argv)

    passes = set(args.only or PASSES)
    try:
        report = check(args.repo, passes, args.fail_on, args.scan, not args.no_write,
                       args.exclude_dir)
    except KeyError as error:
        sys.stderr.write("docdna_check: scan or catalog is missing key %s\n" % error)
        return 2
    except (OSError, ValueError) as error:
        sys.stderr.write("docdna_check: %s\n" % error)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return report["summary"]["exit"]


if __name__ == "__main__":
    sys.exit(main())
