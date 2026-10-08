#!/usr/bin/env python3
"""The claim engine docdna_check.py and docdna_backfill.py --verify share.

Two tools that disagree about which lines of a document are claims, what a citation binds, or which
declarations a covered file holds are worse than either being wrong alone, because a reader cannot
tell which one to believe. Each rule the two tools share is written here once, so neither can drift
from the other.
"""

import hashlib
import os
import re
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from docdna_fs import FileTooLarge, is_file as safe_is_file, read_text as safe_read_text

MAX_FILE_BYTES = 1000000

# A citation names a place, so it binds the numbers written within BIND_LINES lines of that place.
# A GAP marker shields the claim blocks within GAP_REACH lines of it from the citation rule.
BIND_LINES = 4
MAX_SPANS = 20
GAP_REACH = 6

BANNER_OPEN = "Backfilled by docdna"
CONTROL_START = re.compile(r"^##\s+Document control\s*$")
SECTION_HEADING = re.compile(r"^#{1,2}\s")
RULE_LINE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")
TABLE_RULE = re.compile(r"^\|[\s:|-]+\|$")
CONFIDENCE_LINE = re.compile(r"^_Confidence:")
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
PROVENANCE_REGIONS = ("banner", "control")
GAP_QUOTE = re.compile(r"^>\s*\*\*GAP\s+([A-Za-z0-9_.\-]+)\*\*\s*(?:\(([a-z]+)\))?")

CODE_SYMBOL = re.compile(r"\[`([^`\]\s]+)#([^`\]]+)`\]")
CODE_ANCHOR = re.compile(r"\[`([^`\]\s]+)`\s+\"((?:[^\"\\]|\\.)+)\"\]")
RUN_CITE = re.compile(r"\[run:\s*`([^`]+)`\s*->\s*([^\]]+)\]")
REF_CITE = re.compile(r"\[ref:\s*([^\],]+?)(?:,\s*verified\s+(\d{4}-\d{2}-\d{2}))?\]")
HUMAN_CITE = re.compile(r"\[human:\s*(@[^\s\]]+)\s+(\d{4}-\d{2}-\d{2})\]")
LINK_TARGET = re.compile(r"\]\([^)]*\)")
INLINE_CODE = re.compile(r"`([^`]*)`")
PATH_SEGMENT = re.compile(r"^[A-Za-z_.~*@][A-Za-z0-9_.@+~*-]*$")
PATH_EXTENSION = re.compile(r"^\S*\.[A-Za-z][A-Za-z0-9]{0,7}$")
PATH_SPLIT = re.compile(r"[\\/]+")
HAS_LETTER = re.compile(r"[A-Za-z]")

NUMBER_TOKEN = re.compile(r"(?<![A-Za-z0-9_])\d+(?:\.\d+)*")
THOUSANDS = re.compile(r"(?<=\d)[,_](?=\d{3}(?!\d))")
VERSION_TAG = re.compile(r"(?<![A-Za-z0-9_])[vV](?=\d)")
SHA_VALUE = re.compile(r"^[0-9a-fA-F]{7,40}$")
DIGEST_VALUE = re.compile(r"^[A-Za-z][A-Za-z0-9]*:[0-9a-fA-F]{32,}$")
DURATION = re.compile(r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?$")
TIGHT_STAGES = ("assure", "design")

COMMENT_STYLE = {".py": "hash", ".rb": "hash", ".sh": "hash", ".yaml": "hash", ".yml": "hash",
                 ".toml": "hash", ".tf": "hash", ".hcl": "hash", ".prisma": "slash",
                 ".graphql": "hash", ".proto": "slash", ".pl": "hash", ".ex": "hash",
                 ".exs": "hash", ".conf": "hash", ".ini": "hash", ".cfg": "hash",
                 ".js": "slash", ".jsx": "slash", ".mjs": "slash", ".cjs": "slash", ".ts": "slash",
                 ".tsx": "slash", ".go": "slash", ".rs": "slash", ".java": "slash", ".kt": "slash",
                 ".cs": "slash", ".c": "slash", ".cpp": "slash", ".h": "slash", ".php": "slash",
                 ".scala": "slash", ".swift": "slash", ".css": "slash", ".sql": "dash",
                 ".lua": "dash"}

PY_RULES = [r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)",
            r"^\s*class\s+([A-Za-z_]\w*)",
            r"^([A-Za-z_]\w*)\s*(?::[^=]+)?=(?!=)",
            r"^\s*([A-Za-z_]\w*)\s*=\s*(?:[A-Za-z_]\w*\.)?Column\(",
            r"^\s*([A-Za-z_]\w*)\s*=\s*models\.\w+\(",
            r"^\s*@[\w.]*(?:route|get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']"]
JS_RULES = [r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)",
            r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)",
            r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)",
            r"^\s*(?:export\s+)?(?:declare\s+)?(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)",
            r"\b(?:app|router|api|server|fastify)\.(?:get|post|put|patch|delete|use|all)"
            r"\(\s*[\"'`]([^\"'`]+)[\"'`]"]
GO_RULES = [r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)",
            r"^\s*type\s+([A-Za-z_]\w*)",
            r"^\s*(?:var|const)\s+([A-Za-z_]\w*)"]
RUST_RULES = [r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+([A-Za-z_]\w*)",
              r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|type|mod|const|static)"
              r"\s+([A-Za-z_]\w*)"]
JVM_RULES = [r"\b(?:class|interface|enum|record|struct|object|protocol)\s+([A-Za-z_]\w*)",
             r"^\s*(?:public|private|protected|internal)\s+[\w<>\[\],.?]+\s+([A-Za-z_]\w*)\s*\(",
             r"^\s*(?:fun|func)\s+([A-Za-z_]\w*)",
             r"@(?:Get|Post|Put|Patch|Delete|Request)Mapping\(\s*[\"']([^\"']+)[\"']"]
RUBY_RULES = [r"^\s*(?:def|class|module)\s+([A-Za-z_][\w:.]*)",
              r"^\s*(?:get|post|put|patch|delete|resources)\s+[\"':]([^\"',]+)[\"']?"]
PHP_RULES = [r"^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait)\s+(\w+)",
             r"^\s*(?:(?:public|private|protected|static|final|abstract)\s+)*function\s+(\w+)"]
SQL_RULES = [r"(?i)create\s+(?:or\s+replace\s+)?(?:table|view|index|type|function|procedure|"
             r"trigger|schema)\s+(?:if\s+not\s+exists\s+)?([\w.\"]+)",
             r"(?i)^\s*\"?([A-Za-z_]\w*)\"?\s+(?:varchar|text|integer|int|bigint|smallint|serial|"
             r"uuid|bool|boolean|timestamp|timestamptz|date|numeric|decimal|jsonb|json|float|"
             r"double|char|blob|bytea)"]
PRISMA_RULES = [r"^\s*(?:model|enum|type|datasource|generator)\s+(\w+)",
                r"^\s{2,}(\w+)\s+[A-Za-z]"]
GRAPHQL_RULES = [r"^\s*(?:type|input|enum|interface|union|scalar|schema)\s+(\w+)",
                 r"^\s{2,}(\w+)\s*(?:\([^)]*\))?\s*:"]
PROTO_RULES = [r"^\s*(?:message|service|enum)\s+(\w+)", r"^\s*rpc\s+(\w+)",
               r"^\s*(?:required|optional|repeated)?\s*[\w.]+\s+(\w+)\s*=\s*\d+"]
TF_RULES = [r"^\s*(resource|data)\s+\"([^\"]+)\"\s+\"([^\"]+)\"",
            r"^\s*(?:variable|output|module|provider)\s+\"([^\"]+)\""]
KEY_RULES = [r"^\s*-?\s*\"?([A-Za-z0-9_./{}\-]+)\"?\s*:"]
INI_RULES = [r"^\s*\[([^\]]+)\]", r"^\s*([A-Za-z_][\w.\-]*)\s*="]
GENERIC_RULES = [r"^\s*(?:export\s+)?(?:def|func|fn|function|class|struct|interface|type|enum|"
                 r"module|trait)\s+([A-Za-z_][\w.:]*)",
                 r"^\s*([A-Za-z_][\w.\-]*)\s*[:=](?!=)"]

DECL_RULES = {"py": PY_RULES, "js": JS_RULES, "go": GO_RULES, "rust": RUST_RULES, "jvm": JVM_RULES,
              "ruby": RUBY_RULES, "php": PHP_RULES, "sql": SQL_RULES, "prisma": PRISMA_RULES,
              "graphql": GRAPHQL_RULES, "proto": PROTO_RULES, "tf": TF_RULES, "keys": KEY_RULES,
              "ini": INI_RULES, "generic": GENERIC_RULES}
DECL_METHOD = {".py": "py", ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js", ".ts": "js",
               ".tsx": "js", ".svelte": "js", ".vue": "js", ".go": "go", ".rs": "rust",
               ".java": "jvm", ".kt": "jvm", ".cs": "jvm", ".scala": "jvm", ".swift": "jvm",
               ".rb": "ruby", ".php": "php", ".sql": "sql", ".prisma": "prisma",
               ".graphql": "graphql", ".gql": "graphql", ".proto": "proto", ".tf": "tf",
               ".tfvars": "tf", ".hcl": "tf", ".yaml": "keys", ".yml": "keys", ".json": "keys",
               ".toml": "ini", ".ini": "ini", ".cfg": "ini", ".conf": "ini", ".env": "ini",
               ".properties": "ini"}
RULE_CACHE = {}


def as_list(value):
    # A frontmatter key may hold one scalar or a list of them, and a scalar is one entry, never a
    # string to iterate character by character.
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    return [value]


def contained(base, target):
    return target == base or target.startswith(base + os.sep)


def inside_repo(root, full):
    # Both readings have to agree. The lexical one refuses a path that climbs out of the tree with
    # .. or names an absolute location; the resolved one refuses a symlink that points out of the
    # tree, which the lexical reading cannot see. A file reachable only by leaving the repository
    # is not a file in the repository, whichever way it leaves.
    if not contained(os.path.abspath(root), os.path.abspath(full)):
        return False
    return contained(os.path.realpath(root), os.path.realpath(full))


def outside_repo(path):
    return ("path-outside-repo",
            "%s does not resolve inside the repository under analysis. A citation binds numbers "
            "from a file inside that repository, so a path that climbs out of the tree, or names "
            "an absolute location on the machine, names a file no author of this project controls "
            "and is refused rather than bound" % path)


def source_text(root, rel):
    # A covered file, read inside the repository and bounded. A path that leaves the tree, a
    # symlink, a file past the size bound, and a binary file all read as absent, never as text.
    full = os.path.join(os.path.abspath(root), rel)
    if not inside_repo(root, full):
        return None
    resolved = os.path.realpath(full)
    if not safe_is_file(root, resolved):
        return None
    try:
        text = safe_read_text(root, resolved, errors="replace", max_bytes=MAX_FILE_BYTES)
    except (OSError, ValueError, FileTooLarge):
        return None
    if "\x00" in text:
        return None
    return text


def comment_style(rel):
    return COMMENT_STYLE.get(os.path.splitext(rel)[1].lower(), "hash")


def strip_comments(text, style):
    if style == "slash":
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    marker = {"hash": "#", "slash": "//", "dash": "--"}.get(style)
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if marker and stripped.startswith(marker):
            continue
        kept.append(line)
    return kept


def declaration_method(rel):
    ext = os.path.splitext(rel)[1].lower()
    if ext in DECL_METHOD:
        return DECL_METHOD[ext]
    if os.path.basename(rel).lower().startswith(".env"):
        return "ini"
    return "generic"


def rules_for(method):
    if method not in RULE_CACHE:
        RULE_CACHE[method] = [re.compile(pattern) for pattern in DECL_RULES[method]]
    return RULE_CACHE[method]


def extract_declarations(rel, text):
    patterns = rules_for(declaration_method(rel))
    names = set()
    for line in strip_comments(text, comment_style(rel)):
        if not line.strip():
            continue
        for pattern in patterns:
            for match in pattern.finditer(line):
                parts = [part for part in match.groups() if part]
                if not parts:
                    continue
                name = ".".join(part.strip().strip("\"'") for part in parts)
                if name and len(name) <= 200:
                    names.add(name)
    return sorted(names)


def digest_of(entries):
    payload = "\n".join(entries).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def covers_state(root, covers, show=None):
    # The declarations every covered file holds, and the digest over them. docdna_backfill.py
    # stamps this digest into the frontmatter it plans and docdna_check.py recomputes it to measure
    # drift, so the two must be one computation: a document is never drift-stale the moment it is
    # written. show reads a file at an earlier commit instead of from the working tree.
    entries = []
    files = []
    missing = []
    for rel in covers:
        if not isinstance(rel, str):
            continue
        text = source_text(root, rel) if show is None else show(rel)
        if text is None:
            missing.append(rel)
            continue
        names = extract_declarations(rel, text)
        files.append({"path": rel, "declarations": len(names), "method": declaration_method(rel)})
        for name in names:
            entries.append("%s#%s" % (rel, name))
    unique = sorted(set(entries))
    return {"digest": digest_of(unique), "entries": unique, "files": files, "missing": missing}


def is_fence(stripped):
    return stripped.startswith("```") or stripped.startswith("~~~")


def banner_span(lines, start=0):
    for number in range(start, len(lines)):
        if lines[number].strip().lstrip("> ").startswith(BANNER_OPEN):
            return set(range(number, number + 3))
    return set()


def control_span(lines, start=0):
    # The document control block is docdna's own provenance table, so it is read against what
    # docdna derived rather than against citations. It ends at the next heading, and everything
    # after that heading is ordinary prose again.
    first = None
    for number in range(start, len(lines)):
        if CONTROL_START.match(lines[number].strip()):
            first = number
            break
    if first is None:
        return set()
    span = set([first])
    for number in range(first + 1, len(lines)):
        if SECTION_HEADING.match(lines[number].strip()):
            break
        span.add(number)
    return span


def region_of(number, banner, control):
    if number in banner:
        return "banner"
    if number in control:
        return "control"
    return "body"


def quote_text(stripped):
    # A blockquote is the half of a GAP marker a reader actually sees rendered. The GAP id is a
    # label docdna assigns and checks against the machine half, so its digits are not a claim;
    # every other word on the line is.
    text = stripped.lstrip(">").strip()
    if GAP_QUOTE.match(stripped):
        text = text.split("**", 2)[-1].lstrip(":").strip()
    return text


def add_block(blocks, kind, number, text, region):
    blocks.append({"kind": kind, "line": number + 1, "end": number, "text": text, "region": region})


def flush_block(blocks, pending):
    if not pending["text"]:
        return
    blocks.append({"kind": "paragraph", "line": pending["line"], "end": pending["end"],
                   "text": " ".join(pending["text"]), "region": pending["region"]})
    pending["text"] = []


def close_fence(blocks, fence, opened, closed, region):
    # A fence reads to a human as authoritative configuration, so it is treated as verbatim quoted
    # evidence: it joins the claim block that introduces it, and every number inside it has to sit
    # in that block's cited source. A fence nothing introduces is a claim block of its own.
    text = " ".join(fence).strip()
    if not text:
        return
    if blocks and blocks[-1]["region"] == region and opened - blocks[-1]["end"] <= 2:
        blocks[-1]["text"] += " " + text
        blocks[-1]["end"] = closed
        return
    blocks.append({"kind": "fence", "line": opened + 1, "end": closed, "text": text,
                   "region": region})


def claim_blocks(lines, start=0):
    # Every line from start on is read, and line numbers count from the top of the file. Regions
    # differ in what supports them, never in whether they are read: the banner and the document
    # control block are docdna's own provenance and are checked against what docdna derived, a
    # heading and a blockquote are prose, a fence is quoted evidence. The one region not read is an
    # HTML comment, because it is the machine half of a GAP marker and renders to nobody.
    blocks = []
    banner = banner_span(lines, start)
    control = control_span(lines, start)
    headers = set(number - 1 for number in range(start, len(lines))
                  if number > start and TABLE_RULE.match(lines[number].strip()))
    pending = {"text": [], "line": 0, "end": 0, "region": "body"}
    fence = []
    opened = 0
    fenced = False
    comment = False
    for number in range(start, len(lines)):
        raw = lines[number]
        stripped = raw.strip()
        region = region_of(number, banner, control)
        if fenced:
            if is_fence(stripped):
                fenced = False
                close_fence(blocks, fence, opened, number, region)
                fence = []
            else:
                fence.append(stripped)
            continue
        if comment:
            if "-->" in stripped:
                comment = False
            continue
        if stripped.startswith("<!--"):
            flush_block(blocks, pending)
            comment = "-->" not in stripped
            continue
        if is_fence(stripped):
            flush_block(blocks, pending)
            fenced = True
            fence = []
            opened = number
            continue
        if not stripped or RULE_LINE.match(stripped) or TABLE_RULE.match(stripped):
            flush_block(blocks, pending)
            continue
        if CONFIDENCE_LINE.match(stripped) or number in headers:
            # A table header row and the confidence line are labels: a reader sees both, so both
            # are read for numbers, and neither is asked to carry a citation of its own. Dropping
            # them outright made the header row of a table and a one-line confidence note the two
            # cheapest places in a document to park a figure nobody had to answer for.
            flush_block(blocks, pending)
            add_block(blocks, "label", number, stripped, region)
            continue
        if stripped.startswith("#"):
            flush_block(blocks, pending)
            add_block(blocks, "heading", number, stripped.lstrip("#").strip(), region)
            continue
        if stripped.startswith(">"):
            flush_block(blocks, pending)
            add_block(blocks, "quote", number, quote_text(stripped), region)
            continue
        if stripped.startswith("|"):
            flush_block(blocks, pending)
            add_block(blocks, "row", number, stripped, region)
            continue
        if LIST_MARKER.match(raw):
            flush_block(blocks, pending)
            add_block(blocks, "bullet", number, LIST_MARKER.sub("", raw, count=1).strip(), region)
            continue
        indented = raw.startswith(("  ", "\t")) and not pending["text"]
        if blocks and blocks[-1]["kind"] == "bullet" and indented:
            blocks[-1]["text"] += " " + stripped
            blocks[-1]["end"] = number
            continue
        if not pending["text"]:
            pending["line"] = number + 1
            pending["region"] = region
        pending["end"] = number
        pending["text"].append(stripped)
    if fenced and fence:
        close_fence(blocks, fence, opened, len(lines) - 1, region_of(opened, banner, control))
    flush_block(blocks, pending)
    return blocks


def gap_reach(lines):
    # The lines a GAP marker shields from the citation rule, and from that rule alone: a claim block
    # that starts within GAP_REACH lines of a marker is covered by it. The window never shields a
    # number. A GAP marker says a figure is not known, so stating the figure three lines below it
    # is the fabrication the number rule exists for, not an exemption from it.
    covered = set()
    for line in lines:
        for number in range(max(1, line - GAP_REACH), line + GAP_REACH):
            covered.add(number)
    return covered


def anchor_spans(text, anchor):
    # The literal string first, then the same words separated by any whitespace, so an anchor a
    # writer wrapped still names its place.
    spans = []
    start = text.find(anchor)
    while start >= 0 and len(spans) < MAX_SPANS:
        spans.append((start, start + len(anchor)))
        start = text.find(anchor, start + 1)
    if spans:
        return spans
    parts = [re.escape(part) for part in anchor.split()]
    if not parts:
        return []
    loose = re.compile(r"\s+".join(parts))
    return [match.span() for match in loose.finditer(text)][:MAX_SPANS]


def window_around(text, spans):
    # Proximity binding. A citation names a place, so it backs the numbers written at that place:
    # the line the symbol or anchor sits on and BIND_LINES lines either side of it. Without this a
    # citation bought every digit anywhere in the file, so a constants module holding MAX_RETRIES
    # and PAGE_SIZE certified an RTO and an RPO that nobody had ever decided.
    lines = text.splitlines()
    keep = set()
    for start, end in spans:
        first = text.count("\n", 0, start)
        last = text.count("\n", 0, end)
        for number in range(max(0, first - BIND_LINES), min(len(lines), last + BIND_LINES + 1)):
            keep.add(number)
    return "\n".join(lines[number] for number in sorted(keep))


def path_like(value):
    # Path-shaped, not merely slash-bearing. A slash alone made `99.95/month` and `4h/site` look
    # like repository paths and deleted them before the number rule ever saw them. A path has a
    # segment carrying a file extension, or every one of its segments reads as a name.
    text = value.strip()
    if not text or " " in text or "\t" in text:
        return False
    if "/" not in text and "\\" not in text:
        return False
    if not HAS_LETTER.search(text):
        return False
    parts = [part for part in PATH_SPLIT.split(text) if part]
    if not parts:
        return False
    for part in parts:
        if PATH_EXTENSION.match(part):
            return True
    for part in parts:
        if not PATH_SEGMENT.match(part):
            return False
    return True


def strip_path_code(text):
    out = []
    last = 0
    for match in INLINE_CODE.finditer(text):
        out.append(text[last:match.start()])
        out.append(" " if path_like(match.group(1)) else match.group(0))
        last = match.end()
    out.append(text[last:])
    return "".join(out)


def strip_citations(text):
    # What is left is prose the citations do not carry. A citation comes out only in its well-formed
    # shape, so the digits inside a malformed one are still read as a claim. Inline code that names
    # a path is stripped with them: a path is verbatim repository evidence and the digits inside it
    # are not claims. Every other backticked value stays, because "the timeout is `30s`" is a
    # number either way.
    out = text
    for pattern in (CODE_SYMBOL, CODE_ANCHOR, RUN_CITE, REF_CITE, HUMAN_CITE):
        out = pattern.sub(" ", out)
    out = LINK_TARGET.sub(" ", out)
    return strip_path_code(out)


def normalize_numbers(text):
    # 1,000,000 and 1_000_000 and 1000000 are one number written three ways, and v0.2.0 is the same
    # value as 0.2.0. Both sides of every comparison are normalized, so the comma form is not a
    # bypass of the plain form and an underscore in a source file is not a reason to reject a claim
    # that cites it correctly.
    return VERSION_TAG.sub("", THOUSANDS.sub("", text))


def number_tokens(text):
    tokens = []
    for token in NUMBER_TOKEN.findall(normalize_numbers(text)):
        if token not in tokens:
            tokens.append(token)
    return tokens


def number_in(token, text):
    # Digit boundaries, so 621 is not answered by the 1621 that happens to sit in a cited file.
    return re.search(r"(?<![0-9.])%s(?![0-9])" % re.escape(token), text) is not None


def unsupported_numbers(text, support):
    backing = [normalize_numbers(item) for item in support if item]
    return [token for token in number_tokens(text)
            if not [item for item in backing if number_in(token, item)]]


def opaque_identifier(value):
    # A commit sha and a sha256 digest are identifiers, not quantities. Neither is a number in
    # either direction: the digits inside one state nothing about the project, and they answer for
    # no other number either.
    text = str(value).strip()
    return bool(SHA_VALUE.match(text) or DIGEST_VALUE.match(text))


def next_review(cadence, stamp):
    match = DURATION.match(str(cadence) or "")
    if not match:
        return None
    years, months, weeks, days = (int(part) if part else 0 for part in match.groups())
    total = years * 365 + months * 30 + weeks * 7 + days
    if not total:
        return None
    base = datetime.strptime(stamp, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (base + timedelta(days=total)).strftime("%Y-%m-%d")


def derived_policy(entry, data, stamp):
    # The policy values docdna derives for a catalog entry: the frontmatter carries each of them,
    # and each one is the catalog's value or arithmetic on it.
    reviewed = str((data or {}).get("last_reviewed") or stamp)
    try:
        due = next_review(entry.get("cadence"), reviewed)
    except ValueError:
        due = None
    return {"retention": str(entry.get("retention") or "unspecified"),
            "review_cadence": str(entry.get("cadence")),
            "drift_budget": "1" if entry.get("stage") in TIGHT_STAGES else "3",
            "next_review": due or "",
            "valid_until": ""}


def provenance_support(data, entry, gaps, stamp, version, schema):
    # What docdna itself derived for a document: the run stamp, the tool version, the schema, the
    # count of GAP markers actually in the file, every frontmatter value, and the catalog entry
    # behind them, including the cadence, the next review date, the drift budget and any ISO 8601
    # duration the catalog states. The banner and the document control block may state these and
    # nothing else. Identifiers are left out on purpose, so the digits in a commit sha or a digest
    # answer for no number in the banner or the control table.
    parts = [stamp, version, str(schema), str(gaps)]
    for key in sorted(data or {}):
        if key.startswith("__"):
            continue
        value = data[key]
        items = value if isinstance(value, list) else [value]
        parts.extend(str(item) for item in items if not opaque_identifier(item))
    if entry:
        parts.extend(str(entry.get(key) or "") for key in ("cadence", "retention", "title"))
        parts.extend(sorted(derived_policy(entry, data, stamp).values()))
        parts.append(str(next_review(entry.get("cadence"), stamp) or ""))
    return "\n".join(part for part in parts if part)
