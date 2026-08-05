#!/usr/bin/env python3
"""Scan a repository for documentation signals, existing documents, and drift."""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

SCHEMA = 1
TOOL = "docdna_scan"
VERSION = "1.2.0"

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from docdna_fs import (FileTooLarge, bind_root as safe_bind_root,
                       file_size as safe_file_size, listdir as safe_listdir,
                       open_root as safe_open_root, read_text as safe_read_text,
                       root_identity as safe_root_identity,
                       root_is_current as safe_root_is_current,
                       walk_paths as safe_walk_paths)

SIGNALS_PATH = os.path.normpath(os.path.join(HERE, "..", "catalog", "signals.json"))

DOT_ALLOW = {".github", ".gitlab", ".circleci", ".buildkite", ".azure", ".azuredevops",
             ".devcontainer", ".well-known", ".claude", ".cursor", ".windsurf", ".devin",
             ".vscode", ".changeset", ".config", ".vanta"}
IGNORE = {".git", "node_modules", "dist", "build", "out", "target", "vendor", ".next",
          ".svelte-kit", "venv", ".venv", "__pycache__", "coverage", ".terraform",
          ".mypy_cache", ".pytest_cache", ".gradle", "Pods"}
DOC_ROOTS = {"docs", "doc", "documentation"}
STAGE_DIRS = {"frame", "decide", "design", "build", "verify", "assure", "operate", "serve",
              "govern", "retire"}
DENY_READ = (".env",)
DENY_READ_ALLOW = (".example", ".sample", ".template")

# Files docdna writes itself. They stay in the inventory, because DOCDNA.md is govern.manifest and
# llms.txt is build.llms-txt, but they are never read for drift: the report quotes the broken
# command strings it is reporting, so re-reading it turns every run into a new finding about the
# previous run.
SELF_GENERATED = ("DOCDNA.md", "llms.txt")

FAMILIES = ["a11y", "ai", "arch", "data", "deploy", "docs", "iface", "jur", "ops", "proc",
            "qual", "scale", "sec", "supply", "users"]

MAX_FILE_BYTES = 1000000
MAX_READ_FILES = 4000
MAX_LOC_FILES = 1200
MAX_LOG_COMMITS = 2000
MAX_MATCHES_PER_FILE = 200
MAX_DOCS = 500
MAX_DRIFT = 200
MAX_EVIDENCE = 5
MAX_DISTINCT = 20
TEXT_LIMIT = 160
STALE_DAYS = 365
LAG_DAYS = 90
DEEP_DOC_LIMIT = 200
WINDOW_DAYS = 365

STATE_RANK = {"unknown": 0, "absent": 1, "hint": 2, "present": 3}
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
HINT_NOTE = "hint only; may open a question, may never set a verdict"

DOC_EXT = {".md", ".markdown", ".rst", ".adoc", ".txt"}
OPAQUE_EXT = {".docx", ".doc", ".pdf", ".pptx", ".ppt", ".xlsx", ".xls", ".odt", ".rtf"}
TEXT_EXT = {".c", ".cfg", ".cjs", ".conf", ".cpp", ".cs", ".css", ".ex", ".exs", ".go", ".gradle",
            ".graphql", ".h", ".hcl", ".hbs", ".html", ".ini", ".java", ".js", ".json", ".jsx",
            ".kt", ".lua", ".mjs", ".php", ".pl", ".prisma", ".proto", ".py", ".rb", ".rs", ".scala",
            ".sh", ".sql", ".svelte", ".swift", ".tf", ".tfvars", ".toml", ".ts", ".tsx", ".vue",
            ".xml", ".yaml", ".yml", ".zsh"}
LANG_EXT = {".c": "c", ".cpp": "cpp", ".cs": "cs", ".ex": "elixir", ".go": "go", ".java": "java",
            ".js": "js", ".jsx": "js", ".kt": "kotlin", ".lua": "lua", ".mjs": "js", ".php": "php",
            ".py": "py", ".rb": "rb", ".rs": "rs", ".scala": "scala", ".sh": "sh", ".sql": "sql",
            ".svelte": "svelte", ".swift": "swift", ".ts": "ts", ".tsx": "ts", ".vue": "vue"}

# Paths a repository ignores on purpose are not broken references. A document that names
# apps/web/.env.local or node_modules is telling the reader to create or install it, so the absence
# of the path from the index is the point rather than a defect. git check-ignore is the authority
# when git is present, and the names below are the stand-in when it is not.
#
# The stand-in has to stay narrow, because it suppresses findings without being able to justify
# them. GENERATED_NAMES are directory names a tool creates and a human never types: no repository
# keeps documentation in node_modules or __pycache__, so they mean "generated" at any depth.
# GENERATED_ROOTS are ordinary English words. build, dist, out and target only mean "generated" as
# the top of a project; docs/build/ is a documentation directory, and matching the word anywhere in
# a path silences real drift in it.
GENERATED_NAMES = {"node_modules", "__pycache__", ".venv", ".next", ".nuxt", ".svelte-kit",
                   ".terraform", ".mypy_cache", ".pytest_cache", ".gradle", ".turbo",
                   ".parcel-cache"}
GENERATED_ROOTS = {"build", "dist", "out", "target", "coverage", "venv"}
# .env, .env.production and prod.env are the environment file. .envoy and .environment are not, and
# a prefix match cannot tell them apart, so the shape of the whole basename is matched instead.
ENV_BASENAME = re.compile(r"^(?:[A-Za-z0-9_][A-Za-z0-9_.-]*\.env|\.env(?:\.[A-Za-z0-9_.-]+)?)$")
MAX_IGNORE_CHECKS = 500

SECRET_PATH_GLOBS = ["**/.env", "**/.env.*", "**/*.pem", "**/*.key", "**/*.p12", "**/*.pfx",
                     "**/*.jks", "**/*.keystore", "**/*.kdbx", "**/id_rsa*", "**/id_ed25519*",
                     "**/*credential*", "**/*secret*", "**/secrets/**", "**/.npmrc", "**/.pypirc",
                     "**/.netrc"]

REDACTIONS = [
    (re.compile(r"-----BEGIN[^-\n]*PRIVATE KEY-----"), "[redacted private key]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[redacted]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "[redacted]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "[redacted]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "[redacted]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "[redacted]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[redacted]"),
    (re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|"
                r"client[_-]?secret|authorization)\b(\s*[:=]\s*)[\"'][^\s\"'(){}]{8,}[\"']?"),
     "\\1\\2[redacted]"),
]

SPDX_RULES = [
    ("AGPL-3.0", ["gnu affero general public license"]),
    ("GPL-3.0", ["gnu general public license", "version 3"]),
    ("GPL-2.0", ["gnu general public license", "version 2"]),
    ("LGPL-3.0", ["gnu lesser general public license", "version 3"]),
    ("LGPL-2.1", ["gnu lesser general public license", "version 2.1"]),
    ("MPL-2.0", ["mozilla public license"]),
    ("EUPL-1.2", ["european union public licence"]),
    ("SSPL-1.0", ["server side public license"]),
    ("Apache-2.0", ["apache license", "version 2.0"]),
    ("BSD-3-Clause", ["redistribution and use", "neither the name"]),
    ("BSD-2-Clause", ["redistribution and use"]),
    ("ISC", ["permission to use, copy, modify, and/or distribute"]),
    ("MIT", ["permission is hereby granted, free of charge"]),
    ("Unlicense", ["this is free and unencumbered software"]),
    ("CC0-1.0", ["creative commons zero"]),
    ("Zlib", ["altered source versions must be plainly marked"]),
]

SHELL_LANGS = {"", "sh", "bash", "shell", "zsh", "console", "shell-session", "shellsession"}
PM_BUILTINS = {"install", "i", "ci", "add", "remove", "publish", "init", "exec", "x", "create",
               "link", "audit", "outdated", "update", "upgrade", "version", "pack", "why",
               "dlx", "list", "ls", "run", "pm"}
NPM_RUN = re.compile(r"^(npm|pnpm|yarn|bun)\s+(?:run\s+)?(\S+)")
SCRIPT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_.@-]*$")
# A name absent from `scripts` is only a missing script when the command reads that `scripts` table
# at all. Measured on npm 10.9.8, pnpm 11.15.1, yarn 1.22.22 and bun 1.3.11 against a package.json
# holding `build` and `test` and a node_modules/.bin/mytool:
#   npm run mytool                 exit 1, Missing script
#   pnpm run mytool                exit 1, Missing script
#   yarn mytool / yarn run mytool  exit 0, ran node_modules/.bin/mytool
#   bun run mytool / bun mytool    exit 0, ran node_modules/.bin/mytool, and a PATH binary too
#   npm run mytool --if-present    exit 0
#   npm run build --workspaces     exit 0 at a root with no `build`, ran the workspace's script
# So the scripts table settles nothing for a delegating or optional invocation, and it settles the
# manifest but not the outcome for yarn and bun.
PM_DELEGATE = re.compile(r"(?:^|\s)(?:--workspaces?|-w|--recursive|-r|--if-present|"
                         r"--filter(?:=\S*)?|--filter-prod(?:=\S*)?|workspaces?)(?:\s|=|$)")
PM_BIN_FALLBACK = ("yarn", "bun")
BIN_FALLBACK_NOTE = ("yarn and bun run a name absent from `scripts` as a binary from "
                     "node_modules/.bin, which is not committed and was not read")
# setup.py builds its entry points when it runs, so a regex reading of the file is a reading of the
# source, not the list an install puts on the path. That used to be carried as a lower confidence.
# It is a fact about how the name was resolved, so it is now said in the row.
SETUP_PY_NOTE = ("setup.py declares its entry points in code that runs at build time; what was "
                 "read here is the file, not the list an install produces")
# Every command finding reports at "low", exactly as every path finding does. Hand adjudication of
# all 31 command findings across 51 repositories put this check at 1 true positive, and all 27 rows
# that reported "high" were wrong, so the confidence field was anti-correlated with correctness and
# worse than no field at all. 28 of the 30 false positives were documents making no claim about the
# repository they sit in: comparison tables with metasyntactic placeholders, task templates, case
# studies about other repositories, one hypothetical drift example inside an instruction about
# detecting drift. No string-against-manifest test separates those from a command that has gone
# stale, and the recall this pass buys is near zero: across 77 documented commands in 5 maintained
# repositories, none named a script that was missing. So the row still says exactly what it read,
# and it no longer says the reader should believe it. Detection is unchanged; only standing is.
COMMAND_CONFIDENCE = "low"
COMMAND_PRECISION_NOTE = "documents name commands for many reasons; verify before acting"
# `make -C sidecar test` runs in another directory, `make -f build.mk test` reads another makefile
# and `make -j 4 build` puts a flag argument where a target would be, so the first word after
# `make` is not the target. Options are dropped, the ones that carry a separate word take it with
# them, and -C is kept because it says which makefile answers.
MAKE_DIR_OPTS = ("-C", "--directory")
MAKE_FILE_OPTS = ("-f", "--file", "--makefile")
MAKE_ARG_OPTS = ("-I", "--include-dir", "-o", "--old-file", "--assume-old", "-W", "--what-if",
                 "--new-file", "--assume-new", "-j", "--jobs", "-l", "--load-average")
MAKE_NUMBER_OPTS = ("-j", "--jobs", "-l", "--load-average")
MAKE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_.+/%-]*$")
MAKE_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*[+:?!]?=")
# One rule line can declare several targets (`build test:`), a target can be a pattern (`%.pdf:`)
# or computed (`$(BIN):`), and a double-colon rule is still a rule. The left side is read whole and
# split, rather than up to the first space, because `build test:` declares two targets and reading
# one word declares neither.
MAKE_TARGET = re.compile(r"^([^\s:=#][^:=#\n]*?)\s*::?(?!=)")
MAKE_INCLUDE = re.compile(r"^ *[-s]?include\s+(.+?)\s*$")
MAKE_GLOB = ("$", "*", "?", "[")
# GNU make's default .SUFFIXES. `make foo.o` builds foo.o from foo.c with no rule of its own, so a
# name carrying one of these is buildable by a rule the makefile does not contain. Verified with
# GNU Make 3.81: an empty rule set plus foo.c, `make foo.o` exits 0 and compiles it.
MAKE_BUILTIN_SUFFIXES = (".out", ".a", ".ln", ".o", ".c", ".cc", ".C", ".cpp", ".p", ".f", ".F",
                         ".m", ".r", ".y", ".l", ".ym", ".yl", ".s", ".S", ".mod", ".sym", ".def",
                         ".h", ".info", ".dvi", ".tex", ".texinfo", ".texi", ".txinfo", ".w",
                         ".ch", ".web", ".sh", ".elc", ".el")
MANAGE_RUN = re.compile(r"^python[\d.]*\s+manage\.py\s+([A-Za-z0-9_.-]+)")
CARGO_BIN = re.compile(r"^cargo\s+run\b.*?--bin[=\s]+([A-Za-z0-9_.-]+)")
GO_RUN = re.compile(r"^go\s+run\s+(\S+)")
TOML_NAME = re.compile(r"(?m)^\s*name\s*=\s*[\"']([^\"']+)[\"']")
ENTRY_POINT = re.compile(r"(?m)^\s*([A-Za-z0-9_.-]+)\s*=\s*[A-Za-z0-9_.]+:[A-Za-z0-9_.]+")
PROC_LINE = re.compile(r"^[a-z][a-z0-9_-]*:\s+\S")
SERVER_CMDS = ("gunicorn", "uvicorn", "daphne", "hypercorn")
MANAGE_SERVE = {"runserver", "runserver_plus", "runsslserver"}
ENTRY_PREFIXES = ("project.scripts.", "project.gui-scripts.", "tool.poetry.scripts.",
                  "project.entry-points.console_scripts.")
OUTPUT_PREFIXES = (".docdna", "docs/assure/inputs", "sbom")
COUNT_CLAIM = re.compile(r"\b(\d{1,4})\s+(?:api\s+)?(endpoints?|routes?)\b", re.I)
LINK_TARGET = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
CODE_SPAN = re.compile(r"`([^`\n]{2,160})`")
FENCE = re.compile(r"^(?:```+|~~~+)\s*([A-Za-z0-9_+#-]*)")

# A documentation reference names a location. A location is not an expression, so a token carrying
# call syntax, an argument list, an assignment or a quote is code being quoted, not a path.
EXPRESSION_CHARS = ("(", ")", "=", ",", ";", "'", "\"", "`", "&")
# Every language resolves a module specifier by searching extensions, and every documentation site
# routes a page by its slug, so lib/drift-detector and docs/guide are written without one on
# purpose. The reference is to the file the search finds.
MODULE_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".rb", ".go", ".rs", ".java",
              ".kt", ".php", ".vue", ".svelte", ".md", ".mdx")
MODULE_INDEX = ("index", "__init__", "mod")
KNOWN_EXT = TEXT_EXT | DOC_EXT | OPAQUE_EXT
# A reference is a claim that the path is there now. Prose that names a path in order to deny that
# claim is not drifting from the repository, it is describing the repository correctly, and the
# shapes below are the ways a document says so. Each needs structure, not a keyword: a relation
# with a successor on the far side, a negation governing the token, a predicate of absence
# asserted about the token after it has been named, or a verb of removal governing it before it is
# named.
RELOCATION = re.compile(r"(?i)\b(?:renamed?|renaming|moved?|moving|relocated?|replaced?|"
                        r"supersed(?:ed|es)|split|merged|consolidated|extracted)\b")
RELATION = re.compile(r"(?:\s(?:to|into)\s|\s*(?:->|=>|→)\s*)")
PATHISH = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+|[A-Za-z0-9_-]+\.[A-Za-z0-9]{1,6}\b")
NEGATED = re.compile(r"(?i)\bnot\s*[(\[\"'`]*$")
# Only predicates of absence. "legacy", "deprecated" and "formerly" speak to a path's age or
# standing, not to whether it is there, and a deprecated file that is missing is still drift.
ABSENT_CLAIM = re.compile(r"(?i)\bno longer (?:exists?|present|there|available|shipped|included)\b"
                          r"|\b(?:has|have|had|was|were|are|is) been (?:removed|deleted|dropped)\b"
                          r"|\b(?:was|were|are|is|and) (?:removed|deleted|dropped|stale)\b"
                          r"|\bas historical\b|\b(?:is|are|were|was) historical\b"
                          r"|\bdoes not exist\b|\bdo not exist\b|\bno such (?:file|path|directory)\b")
# The same denial pointed forwards. A path a document says is coming is a path the document has
# already told the reader is not there, so it is the aspirational half of ABSENT_CLAIM rather than
# a second kind of claim. "planned" needs a copula in front of it, because "the planned migration
# is described in `docs/x.md`" is a live reference to a document about a plan.
PENDING_CLAIM = re.compile(r"(?i)\bdoes not yet exist\b|\bdo not yet exist\b"
                           r"|\bnot yet (?:created|written|added|implemented|generated|present|"
                           r"available|exists?|in place)\b"
                           r"|\bwill be (?:created|added|written|generated|introduced|provided)\b"
                           r"|\bto be (?:created|added|written|generated|introduced|provided)\b"
                           r"|\b(?:is|are|was|were) (?:still )?planned\b")
# A verb of removal governs the token from in front of it: "Deleted the orphan `x.ts` module."
# The verb only governs when nothing stands between it and the token except the noun phrase it
# heads, which is what keeps "the deleted-items log lives in `docs/x.md`" reportable: the hyphen
# makes "deleted" part of a name rather than a verb, and "lives in" is a second predicate that
# takes the token away from the first. A copula does the same thing, so "the removed helper is
# `src/legacy.js`" names a path that should be there and is not.
REMOVAL_LEAD = re.compile(r"(?i)\b(?:deprecated\s+and\s+(?:removed|deleted)|deleted|removed|"
                          r"dropped|retired|purged|not\s+yet\s+(?:created|added|written))(?![\w-])")
GOVERNED_GAP = re.compile(r"^[\s:'\"`\w-]*$")
NON_GOVERNING = {"is", "are", "was", "were", "be", "been", "being", "remains", "stays", "sits",
                 "lives", "live", "lived", "located", "in", "into", "from", "to", "under", "at",
                 "on", "for", "by", "via", "see", "because", "when", "while", "which", "that",
                 "favor", "favour", "but", "so", "and"}
MAX_GOVERNED_WORDS = 6
# A sentence is the unit that carries the claim, and a wrapped paragraph puts the claim and the
# token on different lines: "... and `schema/agent-manifest.v1.json` does" / "not exist yet." is
# one sentence and two lines. Reading a line at a time reports a path the same line denies.
BLOCK_QUOTE = re.compile(r"^\s*(?:>\s?)+")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s)")
BLOCK_BREAK = re.compile(r"^\s*(?:#{1,6}\s|```|~~~|\||[-=*_]{3,}\s*$)")
SENTENCE_END = re.compile(r"[.!?][\"')\]`]*(?=\s)")
# A wrapped sentence spans two or three lines. Nothing legitimate spans forty, and a document with
# one enormous paragraph should not cost more to read than a document with many.
MAX_BLOCK_LINES = 40
PATH_PRECISION_NOTE = "documents name paths for many reasons; verify before acting"
# What the number counted, said in the row. The OpenAPI reading counts declared paths. The fallback
# counts the lines a route pattern matched, which is a count of matches: two decorators on one
# handler are two lines and one route, so calling it a route count would assert a reading of the
# code that was never done.
OPENAPI_COUNT = "paths declared"
PATTERN_COUNT = "lines matched by the iface.http route pattern"
DRIFT_FILTER_NOTE = ("path findings are a filtered view: the recall gates below drop candidates "
                     "before anything is reported")

GLOB_CACHE = {}
PATTERN_CACHE = {}


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value):
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def iso_z(value):
    stamp = parse_iso(value)
    if stamp is None:
        return None
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def days_since(value):
    stamp = parse_iso(value)
    if stamp is None:
        return None
    delta = datetime.now(timezone.utc) - stamp
    return max(0, int(delta.total_seconds() // 86400))


def glob_re(pattern):
    cached = GLOB_CACHE.get(pattern)
    if cached is not None:
        return cached
    parts = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern[index:index + 3] == "**/":
                parts.append("(?:.*/)?")
                index += 3
                continue
            if pattern[index:index + 2] == "**":
                parts.append(".*")
                index += 2
                continue
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
        index += 1
    compiled = re.compile("^" + "".join(parts) + "$")
    GLOB_CACHE[pattern] = compiled
    return compiled


def glob_match(path, patterns):
    for pattern in patterns or []:
        if glob_re(pattern).match(path):
            return True
    return False


def compile_pattern(pattern, loose=False):
    key = (pattern, loose)
    if key in PATTERN_CACHE:
        return PATTERN_CACHE[key]
    flags = re.M | re.I if loose else re.M
    try:
        compiled = re.compile(pattern, flags)
    except re.error:
        compiled = None
    PATTERN_CACHE[key] = compiled
    return compiled


def denied_read(rel):
    name = os.path.basename(rel)
    if not name.startswith(DENY_READ):
        return False
    return not name.endswith(DENY_READ_ALLOW)


def resolves_inside(root, path):
    root_real = os.path.realpath(root)
    path_real = os.path.realpath(path)
    try:
        return os.path.commonpath([root_real, path_real]) == root_real
    except ValueError:
        return False


def outside_repository(ctx, path, key=None):
    if resolves_inside(ctx["root"], path):
        return False
    marker = key or os.path.realpath(path)
    outside = ctx.setdefault("outside_paths", set())
    if marker not in outside:
        outside.add(marker)
        ctx["scan"]["files_skipped_outside"] += 1
    return True


def record_denied_alias(ctx, rel):
    denied = ctx.setdefault("denied_paths", set())
    if rel not in denied:
        denied.add(rel)
        scan = ctx["scan"]
        scan["files_denied"] = scan.get("files_denied", 0) + 1


def repository_read_path(ctx, rel):
    if denied_read(rel):
        return None
    full = os.path.join(ctx["root"], rel)
    if outside_repository(ctx, full, rel):
        return None
    target = os.path.realpath(full)
    source = os.path.abspath(full)
    if target != source:
        root_real = os.path.realpath(ctx["root"])
        target_rel = os.path.relpath(target, root_real).replace(os.sep, "/")
        indexed = ctx.get("pathset")
        if denied_read(target_rel) or (indexed is not None and target_rel not in indexed):
            record_denied_alias(ctx, rel)
            return None
    return target


def secret_path(rel):
    return glob_match(rel, SECRET_PATH_GLOBS)


def redact(text):
    out = text
    for pattern, replacement in REDACTIONS:
        out = pattern.sub(replacement, out)
    return out


def clip(text):
    return redact(text.strip())[:TEXT_LIMIT]


def evidence_record(rel, line=None, symbol=None, text=None):
    record = {"path": rel}
    if line is not None:
        record["line"] = line
    if secret_path(rel):
        return record
    if symbol is not None:
        record["symbol"] = redact(symbol)[:80]
    if text is not None:
        record["text"] = clip(text)
    return record


def run_git(root, args, timeout=60):
    if not safe_root_is_current(root):
        return None
    descriptor = safe_open_root(root)

    def enter_bound_root():
        os.fchdir(descriptor)

    try:
        proc = subprocess.run(["git"] + args, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=timeout,
                              preexec_fn=enter_bound_root, pass_fds=(descriptor,))
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        os.close(descriptor)
    if proc.returncode != 0 or not safe_root_is_current(root):
        return None
    return proc.stdout.decode("utf-8", "replace")


def git_ignores(root, rel):
    if not safe_root_is_current(root):
        return None
    descriptor = safe_open_root(root)

    def enter_bound_root():
        os.fchdir(descriptor)

    try:
        proc = subprocess.run(["git", "check-ignore", "-q", "--", rel],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
                              preexec_fn=enter_bound_root, pass_fds=(descriptor,))
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        os.close(descriptor)
    if not safe_root_is_current(root):
        return None
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


def builtin_ignored(rel):
    parts = [part for part in rel.split("/") if part and part != "."]
    if not parts:
        return False
    if ENV_BASENAME.match(parts[-1]):
        return True
    if parts[0] in GENERATED_ROOTS:
        return True
    for part in parts:
        if part in GENERATED_NAMES:
            return True
    return False


# git check-ignore is the only authority on what a repository ignores. When it is missing, broken
# or exhausted the scanner is guessing, and a guess that silences findings has to be declared,
# because a reader cannot tell a suppressed finding from an absent one.
def note_fallback(scan, reason):
    scan["ignore_unchecked"] += 1
    if scan["ignore_fallback"] is None:
        scan["ignore_fallback"] = reason


def ignore_source(scan):
    if not scan["ignore_unchecked"]:
        return "git" if scan["ignore_checks"] else "none"
    return "git+builtin" if scan["ignore_answered"] else "builtin"


def ignored_path(ctx, rel):
    cache = ctx["ignored"]
    if rel in cache:
        return cache[rel]
    scan = ctx["scan"]
    verdict = None
    if not ctx["git"]["available"]:
        note_fallback(scan, "no git repository")
    elif scan["ignore_checks"] >= MAX_IGNORE_CHECKS:
        note_fallback(scan, "over %d paths needed an ignore check" % MAX_IGNORE_CHECKS)
    else:
        scan["ignore_checks"] += 1
        verdict = git_ignores(ctx["root"], rel)
        if verdict is None:
            note_fallback(scan, "git check-ignore failed")
        else:
            scan["ignore_answered"] += 1
    if verdict is None:
        verdict = builtin_ignored(rel)
    cache[rel] = verdict
    return verdict


def collect_git(root):
    facts = {"available": False, "head": None, "dirty": None, "tags": 0, "last_commit": None,
             "last_commit_days": None, "commits_window": 0, "authors_window": 0, "authors": [],
             "path_commits": {}, "path_authors": {}, "path_counts": {}, "log_truncated": False}
    head = run_git(root, ["rev-parse", "HEAD"])
    if head is None or not head.strip():
        return facts
    facts["available"] = True
    facts["head"] = head.strip()
    status = run_git(root, ["status", "--porcelain"])
    facts["dirty"] = bool(status.strip()) if status is not None else None
    tags = run_git(root, ["tag", "--list"])
    current_tags = run_git(root, ["tag", "--points-at", "HEAD"])
    all_tags = set(line.strip() for line in (tags or "").splitlines() if line.strip())
    head_tags = set(line.strip() for line in (current_tags or "").splitlines() if line.strip())
    facts["tags"] = len(all_tags - head_tags)
    last = run_git(root, ["log", "--no-merges", "-1", "--format=%aI"])
    if last and last.strip():
        facts["last_commit"] = iso_z(last.strip())
        facts["last_commit_days"] = days_since(last.strip())
    cutoff = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    count = run_git(root, ["rev-list", "--no-merges", "--count", "--since=" + cutoff, "HEAD"])
    if count and count.strip().isdigit():
        facts["commits_window"] = int(count.strip())
    emails = run_git(root, ["log", "--no-merges", "--since=" + cutoff, "--format=%aE"])
    if emails is not None:
        facts["authors_window"] = len(set(line.strip().lower() for line in emails.splitlines()
                                          if line.strip()))
    facts["authors"] = git_shortlog(root)
    collect_git_paths(root, facts)
    return facts


def git_shortlog(root):
    text = run_git(root, ["shortlog", "--no-merges", "-sne", "HEAD"])
    authors = []
    for line in (text or "").splitlines():
        match = re.match(r"^\s*(\d+)\s+(.*?)\s+<([^>]*)>\s*$", line)
        if match:
            authors.append({"name": match.group(2), "commits": int(match.group(1)),
                            "email": match.group(3).lower(), "last": None})
    return authors


def collect_git_paths(root, facts):
    text = run_git(root, ["log", "--no-merges", "-n", str(MAX_LOG_COMMITS), "--name-only",
                          "--format=%x00%H|%aI|%aN"])
    if text is None:
        return
    chunks = text.split("\x00")
    facts["log_truncated"] = len([c for c in chunks if c.strip()]) >= MAX_LOG_COMMITS
    last_by_author = {}
    for chunk in chunks:
        lines = [line for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        header = lines[0].split("|")
        if len(header) < 3:
            continue
        sha, stamp, author = header[0], header[1], "|".join(header[2:])
        if author not in last_by_author or stamp > last_by_author[author]:
            last_by_author[author] = stamp
        for rel in lines[1:]:
            if rel not in facts["path_commits"]:
                facts["path_commits"][rel] = {"sha": sha, "date": stamp, "author": author}
            facts["path_counts"][rel] = facts["path_counts"].get(rel, 0) + 1
            facts["path_authors"].setdefault(rel, Counter())[author] += 1
    for entry in facts["authors"]:
        entry["last"] = (last_by_author.get(entry["name"]) or "")[:10] or None


def prune_dir(name, parent=""):
    if name in STAGE_DIRS and os.path.basename(parent) in DOC_ROOTS:
        return False
    return name in IGNORE or (name.startswith(".") and name not in DOT_ALLOW)


def walk_paths(root):
    return safe_walk_paths(root, prune_dir)


def git_paths(root):
    text = run_git(root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    if text is None:
        return None, set()
    files = []
    pruned = set()
    for rel in text.split("\0"):
        rel = rel.strip()
        if not rel:
            continue
        parts = rel.split("/")[:-1]
        blocked = [part for number, part in enumerate(parts)
                   if prune_dir(part, parts[number - 1] if number else "")]
        if blocked:
            pruned.update(blocked)
            continue
        files.append(rel)
    return sorted(set(files)), pruned


def dirs_from(files):
    out = set()
    for rel in files:
        parts = rel.split("/")
        for stop in range(1, len(parts)):
            out.add("/".join(parts[:stop]))
    return out


def build_index(root):
    files, pruned = git_paths(root)
    source = "git"
    if files is None:
        files, pruned = walk_paths(root)
        source = "walk"
    if os.path.exists(os.path.join(root, ".git")):
        pruned.add(".git")
    dirs = dirs_from(files)
    return {"paths": files, "pathset": set(files), "dirs": dirs, "entries": sorted(set(files) | dirs),
            "basenames": set(os.path.basename(rel) for rel in files),
            "source": source, "pruned": sorted(pruned)}


def read_text(ctx, rel):
    if rel in ctx["cache"]:
        return ctx["cache"][rel]
    text = None
    scan = ctx["scan"]
    full = repository_read_path(ctx, rel)
    if full is None:
        ctx["cache"][rel] = None
        return None
    if scan["files_read"] >= MAX_READ_FILES:
        scan["files_capped"] += 1
        scan["truncated"] = True
    else:
        try:
            text = safe_read_text(ctx["root"], full, errors="replace", max_bytes=MAX_FILE_BYTES)
            scan["files_read"] += 1
        except FileTooLarge:
            scan["files_skipped_large"] += 1
        except (OSError, ValueError):
            scan["read_errors"] += 1
    ctx["cache"][rel] = text
    return text


def scalar(raw):
    text = raw.strip()
    if text.endswith(","):
        text = text[:-1].strip()
    if len(text) > 1 and text[0] in "\"'" and text[-1] == text[0]:
        return text[1:-1]
    if text in ("null", "~", "None", ""):
        return None
    if text in ("true", "True", "yes"):
        return True
    if text in ("false", "False", "no"):
        return False
    if re.match(r"^-?\d+$", text):
        return int(text)
    return text


def flatten_json(value, prefix, flat):
    if isinstance(value, dict):
        for key, child in value.items():
            path = prefix + "." + key if prefix else key
            flat[path] = child
            flatten_json(child, path, flat)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                flatten_json(child, prefix, flat)


def flatten_toml(text):
    flat = {}
    section = ""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        index += 1
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("["):
            section = stripped.strip("[]").strip().strip("\"'")
            flat.setdefault(section, {})
            continue
        match = re.match(r"^([A-Za-z0-9_.\"'-]+)\s*=\s*(.*)$", stripped)
        if not match:
            continue
        name = match.group(1).strip("\"'")
        value = match.group(2)
        if value.startswith("[") and "]" not in value:
            collected = [value]
            while index < len(lines) and "]" not in collected[-1]:
                collected.append(lines[index].strip())
                index += 1
            value = " ".join(collected)
        path = section + "." + name if section else name
        if value.startswith("[") and value.endswith("]"):
            flat[path] = [scalar(part) for part in value[1:-1].split(",") if part.strip()]
        else:
            flat[path] = scalar(value)
    return flat


def manifest_flat(rel, text):
    base = os.path.basename(rel).lower()
    flat = {}
    if base.endswith(".json"):
        try:
            flatten_json(json.loads(text), "", flat)
        except ValueError:
            return {}
        return flat
    if base.endswith(".toml"):
        return flatten_toml(text)
    return {}


def dep_name(raw):
    text = str(raw).strip().strip("\"'")
    text = re.split(r"[\s;]", text)[0]
    text = re.split(r"[<>=!~^\[(]", text)[0]
    return text.strip().lower().replace("_", "-")


def json_deps(flat):
    deps = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies",
                "require", "require-dev"):
        value = flat.get(key)
        if isinstance(value, dict):
            deps.update(dep_name(name) for name in value)
        elif isinstance(value, list):
            deps.update(dep_name(name) for name in value)
    return deps


def toml_deps(flat):
    deps = set()
    for key, value in flat.items():
        tail = key.rsplit(".", 1)
        if isinstance(value, list) and key.endswith("dependencies"):
            deps.update(dep_name(item) for item in value if item)
        elif len(tail) == 2 and (tail[0].endswith("dependencies") or
                                 tail[0].endswith("dev-dependencies")):
            deps.add(dep_name(tail[1]))
    return deps


def text_deps(rel, text):
    base = os.path.basename(rel).lower()
    deps = set()
    if base.startswith("requirements") or base == "constraints.txt":
        for line in text.splitlines():
            line = line.split("#")[0].strip()
            if line and not line.startswith("-"):
                deps.add(dep_name(line))
    elif base == "go.mod":
        for match in re.finditer(r"^\s*(?:require\s+)?([a-z0-9.\-]+\.[a-z]{2,}/[^\s]+)\s+v",
                                 text, re.M):
            deps.add(match.group(1).lower())
    elif base == "gemfile" or base.endswith(".gemspec"):
        for match in re.finditer(r"(?:gem|add_(?:runtime_|development_)?dependency)\s+"
                                 r"[\"']([^\"']+)[\"']", text):
            deps.add(dep_name(match.group(1)))
    elif base == "pom.xml":
        for match in re.finditer(r"<artifactId>\s*([^<\s]+)\s*</artifactId>", text):
            deps.add(dep_name(match.group(1)))
    elif base == "mix.exs":
        for match in re.finditer(r"\{\s*:([a-z0-9_]+)\s*,", text):
            deps.add(dep_name(match.group(1)))
    elif base.startswith("build.gradle"):
        for match in re.finditer(r"[\"']([A-Za-z0-9.\-]+):([A-Za-z0-9.\-]+):", text):
            deps.add(dep_name(match.group(2)))
    elif base in ("environment.yml", "pubspec.yaml", "environment.yaml"):
        for match in re.finditer(r"^\s*[-]?\s*([A-Za-z0-9._-]+)\s*[:=]", text, re.M):
            deps.add(dep_name(match.group(1)))
    elif base in ("setup.py", "setup.cfg"):
        for match in re.finditer(r"[\"']([A-Za-z0-9._-]+)\s*(?:[<>=!~]|[\"'])", text):
            deps.add(dep_name(match.group(1)))
    return deps


def manifest_deps(rel, text, flat):
    base = os.path.basename(rel).lower()
    if base.endswith(".json"):
        return json_deps(flat)
    if base.endswith(".toml"):
        return toml_deps(flat)
    return text_deps(rel, text)


def manifest_has_key(flat, text, key):
    if flat:
        if key in flat:
            return True
        prefix = key + "."
        for name in flat:
            if name.startswith(prefix):
                return True
        return False
    tail = key.rsplit(".", 1)[-1]
    return re.search(r"(?m)^\s*[\"']?" + re.escape(tail) + r"[\"']?\s*[:=]", text) is not None


def manifest_key_set(flat, text, key):
    if not manifest_has_key(flat, text, key):
        return False
    if key in flat:
        return flat[key] is not False and flat[key] is not None
    return True


def line_evidence(rel, text, needle):
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return evidence_record(rel, number, needle, line)
    return evidence_record(rel, 1, needle)


def offset_line(text, offset):
    return text.count("\n", 0, offset) + 1


def offset_text(text, offset):
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    return text[start:end if end != -1 else len(text)]


def predicate(results, node):
    if not isinstance(node, dict):
        return False
    if "all" in node:
        return all(predicate(results, child) for child in node["all"])
    if "any" in node:
        return any(predicate(results, child) for child in node["any"])
    if "not" in node:
        return not predicate(results, node["not"])
    if "always" in node:
        return bool(node["always"])
    if "never" in node:
        return not bool(node["never"])
    if "signal" in node:
        result = results.get(node["signal"])
        if result is None:
            return False
        if "gte" in node:
            return result["state"] == "present" and result["hits"] >= node["gte"]
        if "is" in node:
            return result["state"] == node["is"]
        return result["state"] == "present"
    return False


def clamp_state(state, ceiling):
    if not ceiling or STATE_RANK.get(state, 0) <= STATE_RANK.get(ceiling, 3):
        return state
    if ceiling == "hint" and state == "present":
        return "hint"
    return ceiling


def clamp_confidence(confidence, ceiling):
    if confidence is None or not ceiling:
        return confidence
    if CONFIDENCE_RANK.get(confidence, 2) <= CONFIDENCE_RANK.get(ceiling, 2):
        return confidence
    return ceiling


def finish(sig, state, hits, evidence, max_evidence, detail=None, note=None, confidence="high"):
    state = clamp_state(state, sig.get("max_state"))
    if state == "present" and not evidence:
        raise ValueError("signal %s reported present with no evidence" % sig["id"])
    if state == "hint" and note is None:
        note = HINT_NOTE
    if state == "unknown":
        confidence = None
        evidence = []
    else:
        confidence = clamp_confidence(confidence, sig.get("confidence_cap"))
    record = {"id": sig["id"], "family": sig["family"], "label": sig["label"], "state": state,
              "confidence": confidence, "hits": hits, "evidence": evidence[:max_evidence],
              "evidence_truncated": len(evidence) > max_evidence}
    if detail:
        record["detail"] = detail
    if note:
        record["note"] = note
    return record


def env_name(rel):
    base = os.path.basename(rel)
    if base.startswith(".env."):
        return base[5:]
    if base.startswith("values-"):
        return base[7:].split(".")[0]
    return os.path.splitext(base)[0]


def unit_name(rel):
    parts = rel.split("/")
    if len(parts) >= 3:
        return "/".join(parts[:2])
    if len(parts) == 2:
        return parts[0]
    return rel


def license_spdx(ctx, matched):
    for rel in matched:
        text = read_text(ctx, rel)
        if not text:
            continue
        marker = re.search(r"SPDX-License-Identifier:\s*([A-Za-z0-9.\-+]+)", text)
        if marker:
            return marker.group(1)
        lowered = text[:4000].lower()
        for spdx, needles in SPDX_RULES:
            if all(needle in lowered for needle in needles):
                return spdx
    return None


def detect_path(ctx, sig, detect, max_evidence):
    globs = detect.get("globs") or []
    files = detect.get("files") or []
    excludes = detect.get("exclude_glob") or []
    matched = []
    for rel in ctx["entries"]:
        if excludes and glob_match(rel, excludes):
            continue
        if glob_match(rel, globs) or rel in files or os.path.basename(rel) in files:
            matched.append(rel)
    if not matched:
        return finish(sig, "absent", 0, [], max_evidence)
    only_files = [rel for rel in matched if rel in ctx["pathset"]]
    metric = detect.get("metric")
    detail = None
    hits = len(matched)
    ranked = only_files or matched
    if metric == "files":
        hits = len(only_files)
    elif metric == "lines":
        hits, ranked = count_lines(ctx, only_files)
        detail = {"files": len(only_files)}
    elif metric == "distinct_languages":
        langs = sorted(set(LANG_EXT[os.path.splitext(rel)[1].lower()] for rel in only_files
                           if os.path.splitext(rel)[1].lower() in LANG_EXT))
        hits = len(langs)
        detail = {"distinct": langs[:MAX_DISTINCT]}
    elif metric == "distinct_units":
        units = sorted(set(unit_name(rel) for rel in matched))
        hits = len(units)
        detail = {"distinct": units[:MAX_DISTINCT]}
    elif metric == "distinct_environments":
        names = sorted(set(env_name(rel) for rel in matched if env_name(rel)))
        hits = len(names)
        detail = {"distinct": names[:MAX_DISTINCT]}
    if sig["id"] == "supply.license":
        spdx = license_spdx(ctx, only_files)
        detail = {"spdx": spdx} if spdx else {"spdx": None}
    if hits <= 0:
        return finish(sig, "absent", 0, [], max_evidence, detail)
    evidence = [evidence_record(rel, 1) for rel in ranked[:max_evidence * 2]]
    return finish(sig, "present", hits, evidence, max_evidence, detail)


def count_lines(ctx, paths):
    total = 0
    ranked = []
    for rel in paths[:MAX_LOC_FILES]:
        if os.path.splitext(rel)[1].lower() not in TEXT_EXT | DOC_EXT:
            continue
        text = read_text(ctx, rel)
        if text is None:
            continue
        count = text.count("\n") + 1
        total += count
        ranked.append((count, rel))
    if len(paths) > MAX_LOC_FILES:
        ctx["scan"]["truncated"] = True
    ranked.sort(reverse=True)
    return total, [rel for _, rel in ranked]


def detect_manifest(ctx, sig, detect, max_evidence):
    files = detect.get("files") or []
    excludes = detect.get("exclude_glob") or []
    not_keys = detect.get("not_keys") or []
    keys = detect.get("keys") or []
    wanted = set(dep_name(name) for name in detect.get("deps") or [])
    hits = 0
    evidence = []
    found = []
    seen_manifest = False
    for rel in ctx["paths"]:
        if excludes and glob_match(rel, excludes):
            continue
        if not (rel in files or os.path.basename(rel) in files or glob_match(rel, files)):
            continue
        text = read_text(ctx, rel)
        if text is None:
            continue
        seen_manifest = True
        flat = manifest_flat(rel, text)
        if any(manifest_key_set(flat, text, key) for key in not_keys):
            continue
        declared = manifest_deps(rel, text, flat)
        for name in sorted(wanted & declared):
            hits += 1
            found.append(name)
            evidence.append(line_evidence(rel, text, name))
        for key in keys:
            if manifest_has_key(flat, text, key):
                hits += 1
                found.append(key)
                evidence.append(line_evidence(rel, text, key.rsplit(".", 1)[-1]))
    if not seen_manifest:
        return finish(sig, "absent", 0, [], max_evidence)
    if not hits:
        return finish(sig, "absent", 0, [], max_evidence)
    detail = {"distinct": sorted(set(found))[:MAX_DISTINCT]}
    return finish(sig, "present", hits, evidence, max_evidence, detail)


def grep_candidates(ctx, detect):
    exts = set(detect.get("include_ext") or [])
    globs = detect.get("include_glob") or []
    excludes = detect.get("exclude_glob") or []
    out = []
    for rel in ctx["paths"]:
        ext = os.path.splitext(rel)[1].lower()
        if not ((exts and ext in exts) or (globs and glob_match(rel, globs))):
            continue
        if excludes and glob_match(rel, excludes):
            continue
        out.append(rel)
    return out


def detect_grep(ctx, sig, detect, max_evidence):
    patterns = [compile_pattern(item) for item in detect.get("patterns") or []]
    patterns = [item for item in patterns if item is not None]
    blockers = [compile_pattern(item, True) for item in detect.get("exclude_patterns") or []]
    blockers = [item for item in blockers if item is not None]
    corroborate = detect.get("corroborate") or {}
    corroborators = [compile_pattern(item) for item in corroborate.get("any") or []]
    corroborators = [item for item in corroborators if item is not None]
    scope = corroborate.get("scope") or "same_file"
    per_file = []
    corroborated = False
    for rel in grep_candidates(ctx, detect):
        text = read_text(ctx, rel)
        if text is None:
            continue
        if any(blocker.search(text) for blocker in blockers):
            continue
        support = any(item.search(text) for item in corroborators) if corroborators else True
        corroborated = corroborated or support
        found = []
        for pattern in patterns:
            for match in pattern.finditer(text):
                found.append((match.start(), match.group(0)))
                if len(found) >= MAX_MATCHES_PER_FILE:
                    break
        if not found:
            continue
        if corroborators and scope == "same_file" and not support:
            continue
        per_file.append((rel, text, sorted(found)))
    if corroborators and scope == "repo" and not corroborated:
        per_file = []
    if not per_file:
        return finish(sig, "absent", 0, [], max_evidence)
    hits = 0
    evidence = []
    distinct = set()
    for rel, text, found in per_file:
        hits += len(found)
        for offset, matched in found[:max_evidence]:
            distinct.add(redact(matched.strip())[:40])
            if len(evidence) < max_evidence * 3:
                evidence.append(evidence_record(rel, offset_line(text, offset), matched.strip()[:60],
                                                offset_text(text, offset)))
    detail = {"distinct": sorted(distinct)[:MAX_DISTINCT], "files": len(per_file)}
    confidence = "high" if corroborators else "medium"
    return finish(sig, "present", hits, evidence, max_evidence, detail, None, confidence)


def detect_git(ctx, sig, detect, max_evidence):
    git = ctx["git"]
    if not git["available"]:
        return finish(sig, "unknown", 0, [], max_evidence, None, "no git history available")
    if detect.get("scope") == "per_document":
        return detect_git_documents(ctx, sig, detect, max_evidence)
    metric = detect.get("metric")
    window = detect.get("window_days")
    if metric == "distinct_authors":
        hits = git["authors_window"]
        summary = "%d distinct authors in %d days" % (hits, window or WINDOW_DAYS)
    elif metric == "commit_count":
        hits = git["commits_window"]
        summary = "%d commits in %d days" % (hits, window or WINDOW_DAYS)
    elif metric == "tag_count":
        hits = git["tags"]
        summary = "%d tags" % hits
    elif metric == "days_since_last_commit":
        if git["last_commit_days"] is None:
            return finish(sig, "absent", 0, [], max_evidence)
        hits = git["last_commit_days"]
        summary = "last commit %s" % git["last_commit"]
        evidence = [evidence_record(".git", None, metric, summary)]
        return finish(sig, "present", hits, evidence, max_evidence, {"last_commit": git["last_commit"]})
    else:
        return finish(sig, "unknown", 0, [], max_evidence, None, "unsupported git metric")
    if hits <= 0:
        return finish(sig, "absent", 0, [], max_evidence)
    evidence = [evidence_record(".git", None, metric, summary)]
    return finish(sig, "present", hits, evidence, max_evidence)


def detect_git_documents(ctx, sig, detect, max_evidence):
    docs = ctx["docs"]
    if not ctx["deep"]:
        return finish(sig, "unknown", 0, [], max_evidence, None,
                      "pass 3 skipped; rerun with --deep")
    metric = detect.get("metric")
    threshold = detect.get("threshold_days") or STALE_DAYS
    hits = 0
    evidence = []
    detail = None
    for doc in docs:
        if metric == "last_commit" and doc["last_commit_date"]:
            hits += 1
            evidence.append(evidence_record(doc["path"], None, "last_commit",
                                            doc["last_commit_date"]))
        elif metric == "documents_stale":
            if doc["days_since_commit"] is not None and doc["days_since_commit"] > threshold:
                hits += 1
                evidence.append(evidence_record(doc["path"], None, "days_since_commit",
                                                "%d days" % doc["days_since_commit"]))
        elif metric == "top_author" and doc.get("top_author"):
            hits += 1
            evidence.append(evidence_record(doc["path"], None, "top_author", doc["top_author"]))
        elif metric == "commit_count":
            count = ctx["git"]["path_counts"].get(doc["path"], 0)
            hits += count
            if count:
                evidence.append(evidence_record(doc["path"], None, "commits", "%d commits" % count))
        elif metric == "doc_vs_referenced_code_lag":
            lag = ctx["doc_lag"].get(doc["path"])
            if lag and lag["days"] > (detect.get("threshold_days") or LAG_DAYS):
                hits += 1
                evidence.append(evidence_record(doc["path"], None, lag["code_path"],
                                                "code newer by %d days" % lag["days"]))
    if not hits:
        return finish(sig, "absent", 0, [], max_evidence)
    if metric == "documents_stale":
        detail = {"threshold_days": threshold, "documents": len(docs)}
    return finish(sig, "present", hits, evidence, max_evidence, detail)


def detect_derived(ctx, sig, detect, max_evidence):
    results = ctx["results"]
    depends = detect.get("depends_on") or []
    missing = [name for name in depends if name not in results]
    if missing:
        return finish(sig, "unknown", 0, [], max_evidence, None,
                      "depends on signals that did not run: %s" % ", ".join(sorted(missing)[:3]))
    if not predicate(results, detect.get("when") or {"never": True}):
        return finish(sig, "absent", 0, [], max_evidence)
    match_detail = detect.get("match_detail")
    if match_detail:
        field = match_detail.get("field")
        allowed = match_detail.get("in") or []
        value = None
        for name in depends:
            candidate = (results[name].get("detail") or {}).get(field)
            if candidate is not None:
                value = candidate
                break
        if value not in allowed:
            return finish(sig, "absent", 0, [], max_evidence, {field: value})
    evidence = []
    sources = []
    distinct = []
    hits = 0
    for name in depends:
        result = results[name]
        if result["state"] not in ("present", "hint"):
            continue
        sources.append(name)
        hits += result["hits"]
        evidence.extend(result["evidence"])
        distinct.extend((result.get("detail") or {}).get("distinct") or [])
    detail = {"sources": sources}
    if distinct:
        detail["distinct"] = sorted(set(distinct))[:MAX_DISTINCT]
    if match_detail:
        detail[match_detail.get("field")] = value
    return finish(sig, "present", max(hits, 1), evidence, max_evidence, detail, None, "medium")


DETECTORS = {"path": detect_path, "manifest": detect_manifest, "grep": detect_grep,
             "git": detect_git, "derived": detect_derived}


def load_signals():
    with open(SIGNALS_PATH, encoding="utf-8") as handle:
        registry = json.load(handle)
    return registry.get("signals") or []


def order_signals(signals):
    plain = [sig for sig in signals if (sig.get("detect") or {}).get("kind") != "derived"]
    derived = [sig for sig in signals if (sig.get("detect") or {}).get("kind") == "derived"]
    ordered = sorted(plain, key=lambda sig: sig["id"])
    pending = sorted(derived, key=lambda sig: sig["id"])
    while pending:
        waiting = set(sig["id"] for sig in pending)
        ready = [sig for sig in pending
                 if not waiting & set(sig["detect"].get("depends_on") or [])]
        if not ready:
            break
        ordered.extend(ready)
        chosen = set(sig["id"] for sig in ready)
        pending = [sig for sig in pending if sig["id"] not in chosen]
    return ordered + pending


def run_signal(ctx, sig, max_evidence):
    if sig.get("refuses_to_guess"):
        note = "refuses to guess"
        if sig.get("question"):
            note = "refuses to guess; ask %s" % sig["question"]
        return finish(sig, "unknown", 0, [], max_evidence, None, note)
    if not predicate(ctx["results"], sig.get("gate") or {"always": True}):
        return finish(sig, "unknown", 0, [], max_evidence, None, "gate did not fire")
    detect = sig.get("detect") or {}
    handler = DETECTORS.get(detect.get("kind"))
    if handler is None:
        return finish(sig, "unknown", 0, [], max_evidence, None, "no detector for this signal")
    return handler(ctx, sig, detect, max_evidence)


def run_signals(ctx, signals, families, max_evidence):
    for stage in (1, 2, 3):
        for sig in order_signals([item for item in signals if item.get("pass") == stage]):
            if stage > 1 and families and sig["family"] not in families:
                ctx["results"][sig["id"]] = finish(sig, "unknown", 0, [], max_evidence, None,
                                                   "family not selected")
                continue
            ctx["results"][sig["id"]] = run_signal(ctx, sig, max_evidence)
    return ctx["results"]


def parse_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False, None, None
    end = None
    for number in range(1, len(lines)):
        if lines[number].strip() in ("---", "..."):
            end = number
            break
    if end is None:
        return True, None, "unterminated frontmatter block"
    data = {}
    key = None
    for number in range(1, end):
        stripped = lines[number].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if key is None:
                return True, None, "list item before any key on line %d" % (number + 1)
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(scalar(stripped[2:]))
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", stripped)
        if not match:
            return True, None, "unparsable frontmatter on line %d" % (number + 1)
        key = match.group(1)
        value = match.group(2).strip()
        if not value:
            data[key] = []
        elif value.startswith("[") and value.endswith("]"):
            data[key] = [scalar(part) for part in value[1:-1].split(",") if part.strip()]
        else:
            data[key] = scalar(value)
    return True, data, None


def doc_kind(rel):
    lower = "/" + rel.lower()
    base = os.path.basename(lower)
    if re.search(r"/(adr|adrs|decisions)/", lower) or "-adr-" in base:
        return "adr", "high"
    if base.startswith("readme"):
        return "readme", "high"
    if base.startswith(("changelog", "changes", "history", "news")):
        return "changelog", "high"
    if base.startswith("contributing"):
        return "contributing", "high"
    if base.startswith("code_of_conduct"):
        return "code-of-conduct", "high"
    if base.startswith("security"):
        return "security", "high"
    if base.startswith(("license", "licence", "notice", "copying")):
        return "license", "high"
    if base in ("agents.md", "claude.md", "gemini.md", "copilot-instructions.md"):
        return "agent-instructions", "high"
    if "/.cursor/" in lower or "/.windsurf/" in lower or "/.devin/" in lower:
        return "agent-instructions", "high"
    if "runbook" in lower or "playbook" in lower or "on-call" in lower or "oncall" in lower:
        return "runbook", "high"
    if "/api" in lower or base.startswith("api"):
        return "api-reference", "medium"
    if "architecture" in lower or "/design" in lower or base.startswith("design"):
        return "architecture", "medium"
    if "tutorial" in lower or "how-to" in lower or "howto" in lower or "guide" in lower:
        return "guide", "medium"
    if "getting-started" in lower or "quickstart" in lower:
        return "guide", "medium"
    if "policy" in lower or "governance" in lower or "compliance" in lower:
        return "policy", "medium"
    if "/templates/" in lower or base.startswith("_"):
        return "template", "medium"
    if lower.startswith(("/docs/", "/doc/", "/documentation/")):
        return "documentation", "low"
    return "other", "low"


def doc_links(ctx, rel, text):
    total = 0
    broken = 0
    base = os.path.dirname(rel)
    for target in LINK_TARGET.findall(text):
        total += 1
        cleaned = target.split("#")[0].split("?")[0].strip()
        if not cleaned or "://" in cleaned or cleaned.startswith(("mailto:", "#", "/")):
            continue
        if path_missing(ctx, base, cleaned):
            broken += 1
    return total, broken


def path_variants(base, token):
    out = []
    for candidate in (token, os.path.join(base, token) if base else None):
        if candidate is None:
            continue
        cleaned = os.path.normpath(candidate).replace(os.sep, "/").rstrip("/")
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def resolve_path(ctx, base, token):
    for candidate in path_variants(base, token):
        if candidate in ctx["pathset"] or candidate in ctx["dirs"]:
            return candidate
    return None


def contained(root, rel):
    prefix = os.path.abspath(root)
    target = os.path.abspath(os.path.join(prefix, rel))
    if target != prefix and not target.startswith(prefix + os.sep):
        return False
    return resolves_inside(prefix, target)


def disk_listing(ctx, folder):
    names = ctx["listings"].get(folder)
    if names is None:
        if outside_repository(ctx, folder):
            names = set()
        else:
            try:
                names = set(safe_listdir(ctx["root"], os.path.realpath(folder)))
            except (OSError, ValueError):
                names = set()
        ctx["listings"][folder] = names
    return names


# os.path.exists asks the filesystem, and on macOS and Windows the filesystem answers without
# regard to case, so src/handler.py "exists" in a repository that only holds src/Handler.py. A
# reference is only correct if it spells the entry the way the entry is spelled, and it has to be
# wrong in the same way everywhere, so every component is compared against the real listing.
def disk_entry(ctx, rel):
    folder = ctx["root"]
    for part in rel.split("/"):
        if not part or part == ".":
            continue
        if part not in disk_listing(ctx, folder):
            return False
        folder = os.path.join(folder, part)
        if outside_repository(ctx, folder):
            return False
    return True


# The index decides what docdna reads. The filesystem decides what exists. A gitignored file is
# absent from `git ls-files` and present on disk, and a document that names it is right.
def resolve_disk(ctx, base, token):
    for candidate in path_variants(base, token):
        if not contained(ctx["root"], candidate):
            continue
        if disk_entry(ctx, candidate):
            return candidate
    return None


def ignored_variant(ctx, base, token):
    for candidate in path_variants(base, token):
        if ignored_path(ctx, candidate):
            return candidate
    return None


def path_missing(ctx, base, token):
    if reference_resolves(ctx, base, token):
        return False
    return ignored_variant(ctx, base, token) is None


def normalize_excludes(values):
    out = set()
    for value in values or []:
        cleaned = value.strip().replace(os.sep, "/").strip("/")
        if cleaned.startswith("./"):
            cleaned = cleaned[2:].strip("/")
        if cleaned:
            out.add(cleaned)
    return out


def prune_index(index, excludes):
    keep = lambda rel: not excluded_path(rel, excludes)
    paths = [rel for rel in index["paths"] if keep(rel)]
    pruned = dict(index)
    pruned["paths"] = paths
    pruned["pathset"] = set(paths)
    pruned["dirs"] = set(rel for rel in index["dirs"] if keep(rel))
    pruned["entries"] = [rel for rel in index["entries"] if keep(rel)]
    pruned["basenames"] = set(os.path.basename(rel) for rel in paths)
    return pruned


def excluded_path(rel, excludes):
    for prefix in excludes:
        if rel == prefix or rel.startswith(prefix + "/"):
            return True
    return False


def build_inventory(ctx, generator_globs):
    docs = []
    opaque = []
    counts = Counter()
    for rel in ctx["paths"]:
        if excluded_path(rel, ctx["excludes"]):
            continue
        ext = os.path.splitext(rel)[1].lower()
        if ext in OPAQUE_EXT:
            opaque.append({"path": rel, "bytes": file_bytes(ctx, rel), "parsed": False})
            counts["opaque"] += 1
            continue
        if ext not in DOC_EXT:
            continue
        counts["total"] += 1
        if len(docs) >= MAX_DOCS:
            ctx["scan"]["truncated"] = True
            continue
        docs.append(build_doc(ctx, rel, counts))
    generators = [rel for rel in ctx["entries"] if glob_match(rel, generator_globs)]
    summary = {"total": counts["total"], "opaque": counts["opaque"],
               "with_frontmatter": counts["with_frontmatter"],
               "stale_over_365d": counts["stale"], "broken_links": counts["broken"]}
    return {"docs": docs, "opaque": opaque, "generators": sorted(generators), "counts": summary}


def file_bytes(ctx, rel):
    full = repository_read_path(ctx, rel)
    if full is None:
        return None
    try:
        return safe_file_size(ctx["root"], full)
    except (OSError, ValueError):
        return None


def build_doc(ctx, rel, counts):
    text = read_text(ctx, rel) or ""
    present, data, error = parse_frontmatter(text)
    if present and data:
        counts["with_frontmatter"] += 1
    links_out, links_broken = doc_links(ctx, rel, text)
    counts["broken"] += links_broken
    commit = ctx["git"]["path_commits"].get(rel) or {}
    stamp = commit.get("date")
    age = days_since(stamp) if stamp else None
    if age is not None and age > STALE_DAYS:
        counts["stale"] += 1
    kind, confidence = doc_kind(rel)
    authors = ctx["git"]["path_authors"].get(rel)
    doc = {"path": rel, "kind": kind, "kind_confidence": confidence, "bytes": file_bytes(ctx, rel),
           "frontmatter_present": present, "frontmatter": data,
           "last_commit_sha": (commit.get("sha") or "")[:7] or None,
           "last_commit_date": iso_z(stamp) if stamp else None, "days_since_commit": age,
           "links_out": links_out, "links_broken": links_broken,
           "top_author": authors.most_common(1)[0][0] if authors else None}
    if error:
        doc["frontmatter_error"] = error
    return doc


def strip_prompt(line):
    text = line.strip()
    for prefix in ("$ ", "> ", "% ", "sudo "):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text


def doc_commands(text):
    out = []
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        match = FENCE.match(stripped)
        if match:
            fence = None if fence is not None else (match.group(1) or "").lower()
            continue
        if fence is not None:
            if fence in SHELL_LANGS and stripped and not stripped.startswith("#"):
                out.append((number, strip_prompt(stripped)))
            continue
        for span in CODE_SPAN.findall(line):
            out.append((number, strip_prompt(span)))
    return out


def process_command(text):
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lowered = stripped.lower()
        if not (lowered.startswith(("cmd ", "cmd[", "entrypoint ", "entrypoint[")) or
                PROC_LINE.match(stripped)):
            continue
        for name in SERVER_CMDS:
            if re.search(r"\b%s\b" % name, lowered):
                return name
    return None


def python_manifest(surface, rel):
    folder = os.path.dirname(rel)
    entry = surface["python"].get(folder)
    if entry is None:
        entry = {"dir": folder, "path": rel, "packaged": False,
                 "names": set(), "entries": set()}
        surface["python"][folder] = entry
    return entry


def node_manifest(surface, rel):
    folder = os.path.dirname(rel)
    entry = surface["node"].get(folder)
    if entry is None:
        entry = {"dir": folder, "path": rel, "scripts": {}}
        surface["node"][folder] = entry
    return entry


def make_manifest(surface, rel):
    folder = os.path.dirname(rel)
    entry = surface["make"].get(folder)
    if entry is None:
        entry = {"dir": folder, "path": rel, "targets": set(), "patterns": [],
                 "computed": False, "opaque": False}
        surface["make"][folder] = entry
    return entry


# An included makefile carries targets the including one never names, so a makefile that includes
# is only fully read once the includes are read with it. `include $(wildcard *.mk)` and an include
# of a file that is not in the tree cannot be read, and a target absent from what was read is then
# absent from a partial reading, not from the makefile, so the entry is marked opaque and reports
# nothing. Verified with GNU Make 3.81: a Makefile whose only content is `include extra.mk`, with
# `server:` in extra.mk, runs `make server`.
def include_target(ctx, rel, token):
    for char in MAKE_GLOB:
        if char in token:
            return None
    candidate = os.path.normpath(os.path.join(os.path.dirname(rel), token)).replace(os.sep, "/")
    return candidate if candidate in ctx["pathset"] else None


def read_makefile(ctx, rel, entry, seen):
    text = read_text(ctx, rel)
    if text is None:
        entry["opaque"] = True
        return
    for line in text.splitlines():
        match = MAKE_INCLUDE.match(line)
        if match:
            for token in match.group(1).split():
                target = include_target(ctx, rel, token)
                if target is None:
                    entry["opaque"] = True
                elif target not in seen:
                    seen.add(target)
                    read_makefile(ctx, target, entry, seen)
            continue
        collect_targets(line, entry)


def collect_targets(line, entry):
    match = MAKE_TARGET.match(line)
    if not match:
        return
    for name in match.group(1).split():
        if "$" in name:
            entry["computed"] = True
        elif "%" in name:
            head, _, tail = name.partition("%")
            entry["patterns"].append((head, tail))
        elif not name.startswith("."):
            entry["targets"].add(name)


def pattern_covers(patterns, name):
    for head, tail in patterns:
        if len(name) >= len(head) + len(tail) and name.startswith(head) and name.endswith(tail):
            return True
    return False


def command_surface(ctx):
    surface = {"node": {}, "make": {}, "ci": "", "python": {}, "cargo_path": None,
               "cargo_bins": set(), "go_mod": None, "process_path": None, "process_cmd": None}
    for rel in ctx["paths"]:
        base = os.path.basename(rel)
        if base == "package.json":
            text = read_text(ctx, rel)
            flat = manifest_flat(rel, text or "")
            scripts = flat.get("scripts")
            entry = node_manifest(surface, rel)
            if isinstance(scripts, dict):
                entry["scripts"].update(scripts)
        elif base in ("Makefile", "makefile", "GNUmakefile"):
            read_makefile(ctx, rel, make_manifest(surface, rel), set([rel]))
        elif base == "pyproject.toml":
            text = read_text(ctx, rel) or ""
            flat = flatten_toml(text)
            entry = python_manifest(surface, rel)
            entry["path"] = rel
            for key in ("project.name", "tool.poetry.name"):
                if isinstance(flat.get(key), str):
                    entry["names"].add(dep_name(flat[key]))
            for key in flat:
                plain = key.replace("\"", "").replace("'", "")
                if plain.startswith(ENTRY_PREFIXES):
                    entry["entries"].add(plain.rsplit(".", 1)[-1])
        elif base == "setup.py":
            text = read_text(ctx, rel) or ""
            entry = python_manifest(surface, rel)
            entry["packaged"] = True
            for match in re.finditer(r"[\"']([A-Za-z0-9_.-]+)\s*=\s*[A-Za-z0-9_.]+:[A-Za-z0-9_]+",
                                     text):
                entry["entries"].add(match.group(1))
            for match in re.finditer(r"name\s*=\s*[\"']([A-Za-z0-9_.-]+)[\"']", text):
                entry["names"].add(dep_name(match.group(1)))
        elif base == "setup.cfg":
            text = read_text(ctx, rel) or ""
            entry = python_manifest(surface, rel)
            entry["packaged"] = True
            for match in ENTRY_POINT.finditer(text):
                entry["entries"].add(match.group(1))
            for match in re.finditer(r"(?m)^\s*name\s*=\s*([A-Za-z0-9_.-]+)\s*$", text):
                entry["names"].add(dep_name(match.group(1)))
        elif base == "Cargo.toml":
            text = read_text(ctx, rel) or ""
            if surface["cargo_path"] is None:
                surface["cargo_path"] = rel
            surface["cargo_bins"].update(TOML_NAME.findall(text))
        elif base == "go.mod" and surface["go_mod"] is None:
            surface["go_mod"] = rel
        elif base == "Procfile" or base.startswith("Dockerfile"):
            if surface["process_cmd"] is None:
                found = process_command(read_text(ctx, rel) or "")
                if found:
                    surface["process_path"] = rel
                    surface["process_cmd"] = found
        elif glob_match(rel, [".github/workflows/**", ".gitlab-ci.yml", ".circleci/config.yml",
                              "Jenkinsfile", ".buildkite/**", "azure-pipelines*.yml"]):
            surface["ci"] += (read_text(ctx, rel) or "") + "\n"
    return surface


def all_manifests(byfolder):
    return [byfolder[folder] for folder in sorted(byfolder)]


# A monorepo has one manifest per workspace and one at the root, and which of them answers for a
# command depends on where the document sits. Walk up from the document's own directory, nearest
# first, and finish at the repository root, because a command in a root README is normally run from
# the root. Only the nearest manifest answers: a reader following apps/web/README.md runs the
# command in apps/web, where the root package.json is not consulted at all, so a script declared
# only at the root does not make the documented command work. Anything found further up, or off the
# chain entirely, is a weaker claim, not a silence.
def manifest_chain(byfolder, doc):
    if not byfolder:
        return []
    chain = []
    folder = os.path.dirname(doc)
    while True:
        entry = byfolder.get(folder)
        if entry is not None:
            chain.append(entry)
        if not folder:
            break
        folder = os.path.dirname(folder)
    if not chain and len(byfolder) == 1:
        chain = all_manifests(byfolder)
    return chain


def elsewhere_row(ctx, doc, number, command, name, where, other, field):
    return drift_row(
        doc, "command-not-found", command, other["path"] + ":" + field,
        "`%s` is declared in %s, not in %s, the manifest nearest this document"
        % (name, other["path"], where["path"]), COMMAND_CONFIDENCE, number,
        (commit_day(ctx, doc), commit_day(ctx, where["path"])))


def drift_row(doc, kind, claim, checked_against, detail, confidence, line=None, dates=None):
    row = {"doc": doc, "kind": kind, "claim": claim, "checked_against": checked_against,
           "detail": detail, "confidence": confidence}
    if line is not None:
        row["line"] = line
    if dates:
        row["doc_last_commit"] = dates[0]
        row["code_last_commit"] = dates[1]
    return row


def commit_day(ctx, rel):
    commit = ctx["git"]["path_commits"].get(rel) or {}
    stamp = commit.get("date")
    return stamp[:10] if stamp else None


def node_drift(ctx, doc, number, command, surface):
    match = NPM_RUN.match(command)
    if not match:
        return None
    name = match.group(2)
    if match.group(1) == "npm" and "run" not in command.split()[:2]:
        return None
    # `bun scripts/seed.mjs` executes a file. Only a bare name can be a script in a manifest, so a
    # token carrying a path separator or a file extension is the runtime being handed a program.
    if not SCRIPT_NAME.match(name) or os.path.splitext(name)[1].lower() in KNOWN_EXT:
        return None
    if name in PM_BUILTINS:
        return None
    # A delegating or optional invocation does not read this manifest's scripts, so this manifest
    # cannot answer for it. `yarn workspace web build` lands here as the name `workspace`, which is
    # the same case seen from the other end.
    if PM_DELEGATE.search(command):
        return None
    if name in surface["ci"] or command in surface["ci"]:
        return None
    chain = manifest_chain(surface["node"], doc)
    if not chain:
        return None
    where = chain[0]
    if name in where["scripts"]:
        return None
    for other in all_manifests(surface["node"]):
        if name in other["scripts"]:
            return elsewhere_row(ctx, doc, number, command, name, where, other, "scripts")
    known = ", ".join(sorted(where["scripts"])[:6]) or "none"
    row = drift_row(doc, "command-not-found", command, where["path"] + ":scripts",
                    "no `%s` script in %s; scripts are %s" % (name, where["path"], known),
                    COMMAND_CONFIDENCE, number,
                    (commit_day(ctx, doc), commit_day(ctx, where["path"])))
    if match.group(1) in PM_BIN_FALLBACK:
        row["resolution_note"] = BIN_FALLBACK_NOTE
    return row


def make_invocation(command):
    tokens = command.split()
    if not tokens or tokens[0] != "make":
        return None
    directory = None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("-"):
            if MAKE_ASSIGN.match(token):
                index += 1
                continue
            return (token, directory) if MAKE_NAME.match(token) else None
        head, sep, value = token.partition("=")
        if head in MAKE_FILE_OPTS:
            return None
        if head in MAKE_DIR_OPTS:
            if sep:
                directory = value
            elif index + 1 < len(tokens):
                index += 1
                directory = tokens[index]
            index += 1
            continue
        if head in MAKE_ARG_OPTS and not sep:
            following = tokens[index + 1] if index + 1 < len(tokens) else ""
            index += 1 if head in MAKE_NUMBER_OPTS and not following.isdigit() else 2
            continue
        index += 1
    return None


# `make -C sidecar test` is a claim about sidecar/Makefile, and the makefile nearest the document
# has no say in it. A reader runs the command from the document's directory or from the root, so
# both readings are tried and the first one that has a makefile answers. Neither having one is a
# silence: there is nothing to check the target against.
def make_target_chain(surface, doc, directory):
    if directory is None:
        return manifest_chain(surface["make"], doc)
    bases = [os.path.dirname(doc), ""]
    for base in bases:
        folder = os.path.normpath(os.path.join(base, directory)).replace(os.sep, "/")
        folder = "" if folder == "." else folder
        entry = surface["make"].get(folder)
        if entry is not None:
            return [entry]
    return []


# A target is absent only when the whole rule set was read and nothing in it can produce the name.
# An unread include, a computed target name, a pattern rule that covers the name, a name make can
# build from a built-in suffix rule, and a name that is already a file in the tree are each a way
# for the name to work without appearing in `targets`. Verified with GNU Make 3.81: `make
# README.md` with README.md on disk and no rule for it exits 0 with "Nothing to be done".
def make_unprovable(ctx, where, name):
    if where["opaque"] or where["computed"]:
        return True
    if pattern_covers(where["patterns"], name):
        return True
    if name.endswith(MAKE_BUILTIN_SUFFIXES):
        return True
    plain = name.rstrip("/")
    return plain in ctx["pathset"] or plain in ctx["dirs"]


def make_drift(ctx, doc, number, command, surface):
    invocation = make_invocation(command)
    if invocation is None:
        return None
    name, directory = invocation
    if name in surface["ci"]:
        return None
    chain = make_target_chain(surface, doc, directory)
    if not chain:
        return None
    where = chain[0]
    if name in where["targets"]:
        return None
    if make_unprovable(ctx, where, name):
        return None
    # Only for a command with no -C. With one, the makefile that answers is the one named on the
    # command line, and "the manifest nearest this document" would be the wrong sentence.
    if directory is None:
        for other in all_manifests(surface["make"]):
            if name in other["targets"]:
                return elsewhere_row(ctx, doc, number, command, name, where, other, "targets")
    known = ", ".join(sorted(where["targets"])[:6]) or "none"
    return drift_row(doc, "command-not-found", command, where["path"] + ":targets",
                     "no `%s` target in %s; targets are %s" % (name, where["path"], known),
                     COMMAND_CONFIDENCE, number,
                     (commit_day(ctx, doc), commit_day(ctx, where["path"])))


def manage_drift(ctx, doc, number, command, surface, name):
    if name not in MANAGE_SERVE or not surface["process_cmd"]:
        return None
    return drift_row(
        doc, "command-not-found", command, surface["process_path"] + ":process command",
        "%s runs `%s`; this document runs `manage.py %s`"
        % (surface["process_path"], surface["process_cmd"], name),
        COMMAND_CONFIDENCE, number,
        (commit_day(ctx, doc), commit_day(ctx, surface["process_path"])))


def declares_entry(entry, wanted):
    return wanted in set(dep_name(item) for item in entry["entries"])


def script_drift(ctx, doc, number, command, chain, surface):
    name = command.split()[0]
    wanted = dep_name(name)
    claimed = [entry for entry in chain if wanted in entry["names"]]
    if not claimed:
        return None
    where = claimed[0]
    if declares_entry(where, wanted):
        return None
    for other in all_manifests(surface["python"]):
        if declares_entry(other, wanted):
            return elsewhere_row(ctx, doc, number, command, name, where, other, "project.scripts")
    known = ", ".join(sorted(where["entries"])[:6]) or "none"
    row = drift_row(
        doc, "command-not-found", command, where["path"] + ":project.scripts",
        "no console script named `%s` in %s; declared entry points are %s"
        % (name, where["path"], known),
        COMMAND_CONFIDENCE, number, (commit_day(ctx, doc), commit_day(ctx, where["path"])))
    if where["packaged"]:
        row["resolution_note"] = SETUP_PY_NOTE
    return row


def python_drift(ctx, doc, number, command, surface):
    match = MANAGE_RUN.match(command)
    if match:
        return manage_drift(ctx, doc, number, command, surface, match.group(1))
    return script_drift(ctx, doc, number, command,
                        manifest_chain(surface["python"], doc), surface)


def cargo_drift(ctx, doc, number, command, surface):
    match = CARGO_BIN.match(command)
    if not match or not surface["cargo_bins"]:
        return None
    name = match.group(1)
    if name in surface["cargo_bins"]:
        return None
    known = ", ".join(sorted(surface["cargo_bins"])[:6])
    return drift_row(
        doc, "command-not-found", command, surface["cargo_path"] + ":bin",
        "no `%s` among the `name` entries in the Cargo.toml files; the names read are %s"
        % (name, known),
        COMMAND_CONFIDENCE, number,
        (commit_day(ctx, doc), commit_day(ctx, surface["cargo_path"])))


def go_drift(ctx, doc, number, command, surface):
    match = GO_RUN.match(command)
    if not match or not surface["go_mod"]:
        return None
    target = match.group(1)
    if not (target.startswith("./") or target.endswith(".go")):
        return None
    candidate = path_candidate(target[2:] if target.startswith("./") else target)
    if candidate is None or candidate in ctx["pathset"] or candidate in ctx["dirs"]:
        return None
    return drift_row(
        doc, "command-not-found", command, surface["go_mod"] + ":module",
        "no `%s` file or directory in the repository" % target, COMMAND_CONFIDENCE, number,
        (commit_day(ctx, doc), commit_day(ctx, surface["go_mod"])))


def check_commands(ctx, doc, text, surface):
    rows = []
    for number, command in doc_commands(text):
        if not command.split():
            continue
        row = (node_drift(ctx, doc, number, command, surface) or
               make_drift(ctx, doc, number, command, surface) or
               python_drift(ctx, doc, number, command, surface) or
               cargo_drift(ctx, doc, number, command, surface) or
               go_drift(ctx, doc, number, command, surface))
        if row:
            # Stamped here rather than at six call sites, so no runtime can be added that emits a
            # command row without the caveat that the measurement says every command row carries.
            row["precision_note"] = COMMAND_PRECISION_NOTE
            rows.append(row)
    return rows


def path_tokens(text):
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        for span in CODE_SPAN.findall(line):
            out.append((number, span.strip(), "code"))
        for target in LINK_TARGET.findall(line):
            out.append((number, target.split("#")[0].split("?")[0].strip(), "link"))
    return out


def path_candidate(token):
    text = token.strip()
    # A fragment addresses a symbol or a heading inside a file, so lib/profiles.js#listPacks names
    # lib/profiles.js. The fragment is never part of the filename.
    text = text.split("#", 1)[0].split("?", 1)[0]
    # Trailing punctuation belongs to the sentence, so it comes off. A leading dot belongs to the
    # name: .github and .env.example are the paths they look like, and stripping the dot invents a
    # different path that was never referenced and reports it missing.
    text = text.rstrip(",.;:!?")
    if ")" in text and "(" not in text:
        text = text.rstrip(")")
    text = re.sub(r":[\d,\-]+$", "", text)
    if not text or len(text) > 120:
        return None
    if text.split() != [text]:
        return None
    if text.startswith(("http", "mailto:", "#", "@", "-", "<", "$", "/", "~", "!")):
        return None
    for bad in ("://", "*", "?", "<", ">", "{", "}", "$", "|", "..", "\\") + EXPRESSION_CHARS:
        if bad in text:
            return None
    if text.startswith("./"):
        text = text[2:]
    # A trailing slash is the writer stating that the reference is a directory, which is evidence
    # of a path on its own; without one, a bare word with no extension is just a word.
    folder = text.endswith("/")
    text = text.rstrip("/")
    if not text:
        return None
    extension = os.path.splitext(text)[1].lower()
    if "/" not in text and not folder and extension not in TEXT_EXT | DOC_EXT:
        return None
    return text


def resolve_any(ctx, base, candidate):
    if resolve_path(ctx, base, candidate) is not None:
        return True
    return resolve_disk(ctx, base, candidate) is not None


def module_resolves(ctx, base, candidate):
    for ext in MODULE_EXT:
        if resolve_any(ctx, base, candidate + ext):
            return True
    for stem in MODULE_INDEX:
        for ext in MODULE_EXT:
            if resolve_any(ctx, base, candidate + "/" + stem + ext):
                return True
    return False


# lib/pillars.init(projectRoot) is a call and is rejected before it gets here. lib/pillars.init is
# the same expression with the argument list left off, and it is recognisable by what it resolves
# to: a module, plus a tail that is not any file extension. That tail selects something inside the
# module, exactly as a fragment does, so the module is the reference.
def member_access(ctx, base, candidate):
    stem, extension = os.path.splitext(candidate)
    if not extension or "/" not in stem or extension.lower() in KNOWN_EXT:
        return False
    return resolve_any(ctx, base, stem) or module_resolves(ctx, base, stem)


def reference_resolves(ctx, base, candidate):
    if resolve_any(ctx, base, candidate):
        return True
    if module_resolves(ctx, base, candidate):
        return True
    return member_access(ctx, base, candidate)


# The construction is a verb of relocation, then this token, then a relation, then a second path.
# All three are required: a line that merely contains "moved" is not naming a history, and a token
# with nothing on the far side of the arrow has no successor to have been renamed to.
def relocated_from(head, tail):
    if not RELOCATION.search(head + tail):
        return False
    match = RELATION.search(tail)
    if match is None:
        return False
    return PATHISH.search(tail[match.end():]) is not None


# A predicate of absence asserted about the token comes after it: "`config/` was removed". A verb
# of removal that takes the token as its object comes before it: "Deleted `config/`". Both are the
# document saying the path is gone. What separates them from "the legacy layout lives in
# `config/`", where the adjective in front is not a claim about presence at all, is that the verb
# has to reach the token: only the noun phrase it heads may stand between them, and a copula, a
# preposition or a second predicate ends its reach.
def governed_removal(head):
    lead = None
    for match in REMOVAL_LEAD.finditer(head):
        lead = match
    if lead is None:
        return False
    gap = head[lead.end():]
    if GOVERNED_GAP.match(gap) is None:
        return False
    words = gap.replace("-", " ").split()
    if len(words) > MAX_GOVERNED_WORDS:
        return False
    return not any(word.strip("'\"`").lower() in NON_GOVERNING for word in words)


def denied_presence(head, tail):
    if NEGATED.search(head) is not None or governed_removal(head):
        return True
    return ABSENT_CLAIM.search(tail) is not None or PENDING_CLAIM.search(tail) is not None


def historical_mention(sentence, token):
    start = sentence.find(token)
    if start < 0:
        return False
    head, tail = sentence[:start], sentence[start + len(token):]
    return relocated_from(head, tail) or denied_presence(head, tail)


# The sentence is the unit that carries the claim, and it is not always wider than the line: a line
# holding two sentences denies the token in one of them and not the other. Narrowing to the
# sentence alone would start reporting paths the previous release was silent about, so both scopes
# are asked and either one suppresses. For a check whose whole failure mode is over-reporting, the
# wider answer is the safe one, and a denial that only the line can see stays a denial.
def denied_reference(lines, index, token):
    line = lines[index] if 0 <= index < len(lines) else ""
    if historical_mention(line, token):
        return True
    scope = sentence_scope(lines, index, token)
    return scope != line and historical_mention(scope, token)


def block_body(line):
    return LIST_ITEM.sub("", BLOCK_QUOTE.sub("", line), count=1)


def block_break(line):
    return not line.strip() or BLOCK_BREAK.match(BLOCK_QUOTE.sub("", line)) is not None


# The block is the paragraph, list item or block quote the line sits in. A list item starts one and
# a heading, a fence, a table row or a blank line ends one, so joining the rest reconstructs the
# wrapped sentence without merging two bullets that happen to be adjacent.
def block_bounds(lines, index):
    floor = max(0, index - MAX_BLOCK_LINES)
    ceiling = min(len(lines) - 1, index + MAX_BLOCK_LINES)
    start = index
    while start > floor and LIST_ITEM.match(BLOCK_QUOTE.sub("", lines[start])) is None:
        if block_break(lines[start - 1]):
            break
        start -= 1
    end = index
    while end < ceiling:
        following = lines[end + 1]
        if block_break(following) or LIST_ITEM.match(BLOCK_QUOTE.sub("", following)) is not None:
            break
        end += 1
    return start, end


def sentence_scope(lines, index, token):
    if index < 0 or index >= len(lines):
        return ""
    start, end = block_bounds(lines, index)
    pieces = [block_body(line) for line in lines[start:end + 1]]
    text = " ".join(pieces)
    offset = len(" ".join(pieces[:index - start]))
    if index > start:
        offset += 1
    at = text.find(token, offset)
    if at < 0:
        at = text.find(token)
    if at < 0:
        return lines[index]
    opening = 0
    for match in SENTENCE_END.finditer(text):
        if match.end() > at:
            break
        opening = match.end()
    closing = len(text)
    for match in SENTENCE_END.finditer(text, at + len(token)):
        closing = match.end()
        break
    return text[opening:closing]


def output_path(candidate):
    for prefix in OUTPUT_PREFIXES:
        if candidate == prefix or candidate.startswith(prefix + "/"):
            return True
    return False


def note_discard(ctx, reason):
    counts = ctx["scan"]["drift"]["discarded"]
    counts[reason] = counts.get(reason, 0) + 1


# The gates below decide what is reported, and the strings they drop are never seen again, so each
# one is counted. Two of them trade recall for precision rather than judging a reference: a bare
# filename outside a link is not treated as a path at all, and a candidate whose first component is
# not a directory in this repository is dropped whether or not it is a real reference. In a large
# repository that second gate discards three orders of magnitude more candidates than the report
# ends up carrying, which is the difference between a filtered view and a complete one.
def check_paths(ctx, doc, text):
    rows = []
    base = os.path.dirname(doc)
    lines = text.splitlines()
    seen = set()
    for number, token, source in path_tokens(text):
        candidate = path_candidate(token)
        if candidate is None or candidate in seen:
            continue
        if denied_reference(lines, number - 1, token):
            continue
        seen.add(candidate)
        ctx["scan"]["drift"]["candidates"] += 1
        if reference_resolves(ctx, base, candidate):
            continue
        if output_path(candidate):
            continue
        if os.path.basename(candidate) in ctx["basenames"]:
            note_discard(ctx, "basename_found_elsewhere")
            continue
        parent = os.path.dirname(candidate)
        first = candidate.split("/")[0]
        if not parent:
            if source != "link":
                note_discard(ctx, "bare_name_outside_a_link")
                continue
        elif parent not in ctx["dirs"] and first not in ctx["dirs"]:
            note_discard(ctx, "first_component_not_a_directory")
            continue
        if ignored_variant(ctx, base, candidate) is not None:
            continue
        # A path-not-found finding is a string that is not on disk, and a document names a path for
        # many reasons other than asserting it is there now: an install target, a changelog entry,
        # a cross-repository reference, a hypothetical, a recommendation. Hand-adjudicating every
        # finding on five repositories put the precision of this check at 11 percent, so it reports
        # at "low" and says why in the row. The gates above are unchanged; only the claim is.
        row = drift_row(doc, "path-not-found", candidate, "working tree",
                        "no such file or directory in the repository", "low", number)
        row["precision_note"] = PATH_PRECISION_NOTE
        rows.append(row)
    return rows


def openapi_routes(ctx):
    for rel in ctx["paths"]:
        base = os.path.basename(rel).lower()
        if not (base.startswith(("openapi", "swagger")) and
                base.endswith((".json", ".yaml", ".yml"))):
            continue
        text = read_text(ctx, rel)
        if not text:
            continue
        if base.endswith(".json"):
            try:
                data = json.loads(text)
            except ValueError:
                continue
            count = len(data.get("paths") or {})
        else:
            count = len(re.findall(r"^\s{2}/\S*:\s*$", text, re.M))
        if count:
            return count, rel
    return 0, None


def check_counts(ctx, doc, text, routes, routes_path, source):
    rows = []
    if not routes:
        return rows
    for number, line in enumerate(text.splitlines(), 1):
        for match in COUNT_CLAIM.finditer(line):
            claimed = int(match.group(1))
            if claimed == routes:
                continue
            rows.append(drift_row(
                doc, "count-mismatch", "%s %s" % (match.group(1), match.group(2)), routes_path,
                "%d %s in %s" % (routes, source, routes_path), "medium", number,
                (commit_day(ctx, doc), commit_day(ctx, routes_path))))
    return rows


def doc_references(ctx, docs):
    lag = {}
    for doc in docs:
        rel = doc["path"]
        text = ctx["cache"].get(rel) or ""
        base = os.path.dirname(rel)
        named = []
        for _, token, _source in path_tokens(text):
            candidate = path_candidate(token)
            if candidate is None:
                continue
            resolved = resolve_path(ctx, base, candidate)
            if resolved and resolved in ctx["pathset"] and resolved != rel:
                named.append(resolved)
        named = sorted(set(named))
        doc_stamp = parse_iso(doc["last_commit_date"])
        if doc_stamp is None:
            continue
        newest = None
        newest_path = None
        for code in named:
            commit = ctx["git"]["path_commits"].get(code) or {}
            stamp = parse_iso(commit.get("date"))
            if stamp and (newest is None or stamp > newest):
                newest = stamp
                newest_path = code
        if newest is None:
            continue
        days = int((newest - doc_stamp).total_seconds() // 86400)
        if days > 0:
            lag[rel] = {"days": days, "code_path": newest_path,
                        "code_date": newest.strftime("%Y-%m-%d"),
                        "doc_date": doc_stamp.strftime("%Y-%m-%d")}
    return lag


def drift_stats():
    return {"candidates": 0, "found": 0, "emitted": 0, "limit": MAX_DRIFT, "truncated": False,
            "discarded": {"basename_found_elsewhere": 0, "bare_name_outside_a_link": 0,
                          "first_component_not_a_directory": 0},
            "note": DRIFT_FILTER_NOTE}


def build_drift(ctx, docs):
    surface = command_surface(ctx)
    routes, routes_path = openapi_routes(ctx)
    source = OPENAPI_COUNT
    if not routes:
        http = ctx["results"].get("iface.http") or {}
        if http.get("state") == "present":
            routes = http["hits"]
            routes_path = (http["evidence"][0]["path"] if http.get("evidence") else "iface.http")
            source = PATTERN_COUNT
    rows = []
    for doc in docs:
        rel = doc["path"]
        if rel in SELF_GENERATED:
            continue
        if os.path.splitext(rel)[1].lower() not in (".md", ".markdown"):
            continue
        text = ctx["cache"].get(rel)
        if not text:
            continue
        rows.extend(check_commands(ctx, rel, text, surface))
        rows.extend(check_paths(ctx, rel, text))
        rows.extend(check_counts(ctx, rel, text, routes, routes_path, source))
        lag = ctx["doc_lag"].get(rel)
        if lag and lag["days"] > LAG_DAYS:
            rows.append(drift_row(
                rel, "stale-vs-code", "documents %s" % lag["code_path"], lag["code_path"],
                "code changed %d days after the document was last touched" % lag["days"],
                "high" if lag["days"] > STALE_DAYS else "medium", None,
                (lag["doc_date"], lag["code_date"])))
    rows.sort(key=lambda row: (row["doc"], row.get("line") or 0, row["kind"]))
    # The count before the cut, not just the fact of one. A report that swallowed 900 findings and
    # a report that swallowed 3 both hit the limit, and a reader cannot act on the same sentence.
    stats = ctx["scan"]["drift"]
    stats["found"] = len(rows)
    if len(rows) > MAX_DRIFT:
        ctx["scan"]["truncated"] = True
        stats["truncated"] = True
    kept = rows[:MAX_DRIFT]
    stats["emitted"] = len(kept)
    return kept


def build_ownership(ctx):
    owners = None
    for candidate in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS",
                      ".gitlab/CODEOWNERS"):
        if candidate in ctx["pathset"]:
            owners = candidate
            break
    rules = 0
    if owners:
        text = read_text(ctx, owners) or ""
        rules = len([line for line in text.splitlines()
                     if line.strip() and not line.strip().startswith("#")])
    top = [{"name": entry["name"], "commits": entry["commits"], "last": entry["last"]}
           for entry in ctx["git"]["authors"][:10]]
    buckets = {}
    for rel, authors in ctx["git"]["path_authors"].items():
        if rel not in ctx["pathset"]:
            continue
        top_dir = rel.split("/")[0] + "/" if "/" in rel else "."
        bucket = buckets.setdefault(top_dir, {"authors": set(), "files": set()})
        bucket["authors"].update(authors)
        bucket["files"].add(rel)
    single = [{"path": name, "authors": 1} for name, bucket in sorted(buckets.items())
              if len(bucket["authors"]) == 1 and len(bucket["files"]) > 1]
    return {"codeowners": bool(owners), "codeowners_path": owners, "rules": rules,
            "top_authors": top, "single_author_paths": single[:10]}


def build_unknown(ctx, signals, results, families):
    by_family = {}
    for sig in signals:
        result = results.get(sig["id"])
        if result is None or result["state"] != "unknown":
            continue
        if families and sig["family"] not in families:
            continue
        by_family.setdefault(sig["family"], []).append((sig, result))
    rows = []
    for family in sorted(by_family):
        asked = sorted(set(sig["question"] for sig, _ in by_family[family] if sig.get("question")))
        notes = Counter(result.get("note") or "not evaluated" for _, result in by_family[family])
        reason = "%d signals unknown: %s" % (len(by_family[family]), notes.most_common(1)[0][0])
        if asked:
            reason += "; resolved by %s" % ", ".join(asked)
        rows.append({"family": family, "reason": reason})
    return rows


def scan(root, families, deep, max_evidence, excludes=None):
    root = safe_bind_root(os.path.abspath(root))
    try:
        return scan_bound(root, families, deep, max_evidence, excludes)
    finally:
        root.close()


def scan_bound(root, families, deep, max_evidence, excludes=None):
    device, inode = safe_root_identity(root)
    index = build_index(root)
    denied = [rel for rel in index["paths"] if denied_read(rel)]
    excludes = normalize_excludes(excludes)
    # An excluded directory leaves the SIGNAL index too, not only the document and drift passes. A
    # repository that vendors another project under fixtures/ or examples/ otherwise has that
    # project's manifests read as its own: one demo depending on fhirclient made this repository
    # report a health overlay and claim that card data crossed it. Naming a directory as not part of
    # this project has to mean the archetype stops reading it.
    if excludes:
        index = prune_index(index, excludes)
    ctx = {"root": root, "paths": index["paths"], "pathset": index["pathset"],
           "dirs": index["dirs"], "entries": index["entries"], "basenames": index["basenames"],
           "cache": {}, "results": {}, "docs": [], "doc_lag": {}, "deep": deep,
           "denied_paths": set(denied),
           "excludes": excludes, "git": collect_git(root), "ignored": {}, "listings": {},
           "scan": {"files_total": len(index["paths"]), "files_read": 0, "files_skipped_large": 0,
                    "files_skipped_outside": 0, "files_denied": len(denied),
                    "files_capped": 0, "read_errors": 0,
                    "dirs_pruned": index["pruned"], "dirs_excluded": sorted(excludes),
                    "index_source": index["source"], "ignore_checks": 0, "ignore_answered": 0,
                    "ignore_unchecked": 0, "ignore_fallback": None, "ignore_source": "none",
                    "max_file_bytes": MAX_FILE_BYTES, "truncated": False,
                    "drift": drift_stats()}}
    signals = load_signals()
    generator_globs = []
    for sig in signals:
        if sig["id"] == "docs.site_generator":
            generator_globs = (sig.get("detect") or {}).get("globs") or []
    inventory = build_inventory(ctx, generator_globs)
    ctx["docs"] = inventory["docs"]
    if not deep and len(inventory["docs"]) <= DEEP_DOC_LIMIT and ctx["git"]["available"]:
        ctx["deep"] = True
    ctx["doc_lag"] = doc_references(ctx, inventory["docs"])
    results = run_signals(ctx, signals, families, max_evidence)
    drift = build_drift(ctx, inventory["docs"])
    ctx["scan"]["ignore_source"] = ignore_source(ctx["scan"])
    emitted = [results[sig["id"]] for sig in sorted(signals, key=lambda item: item["id"])
               if sig["id"] in results and (not families or sig["family"] in families)]
    for doc in inventory["docs"]:
        doc.pop("top_author", None)
    return {"schema": SCHEMA, "tool": TOOL, "version": VERSION, "generated": now_utc(),
            "root": root, "root_identity": {"device": device, "inode": inode},
            "commit": ctx["git"]["head"], "dirty": ctx["git"]["dirty"],
            "scan": ctx["scan"], "signals": emitted, "inventory": inventory, "drift": drift,
            "ownership": build_ownership(ctx),
            "unknown": build_unknown(ctx, signals, results, families)}


def print_text(report):
    counts = Counter(item["state"] for item in report["signals"])
    scan_stats = report["scan"]
    inventory = report["inventory"]["counts"]
    print("docdna scan %s" % VERSION)
    print("  %-9s: %s" % ("root", report["root"]))
    head = report["commit"][:12] if report["commit"] else "no git history"
    print("  %-9s: %s (%s index)" % ("commit", head, scan_stats["index_source"]))
    if report["dirty"]:
        print("  %-9s: %s" % ("worktree", "dirty"))
    print("  %-9s: %d indexed, %d read, %d denied, %d outside, %d unreadable"
          % ("files", scan_stats["files_total"], scan_stats["files_read"],
             scan_stats["files_denied"], scan_stats["files_skipped_outside"],
             scan_stats["read_errors"]))
    print("  %-9s: %d present, %d hint, %d absent, %d unknown"
          % ("signals", counts["present"], counts["hint"], counts["absent"], counts["unknown"]))
    print("  %-9s: %d markdown, %d opaque, %d with frontmatter"
          % ("docs", inventory["total"], inventory["opaque"], inventory["with_frontmatter"]))
    print("  %-9s: %d over %d days, %d broken links"
          % ("stale", inventory["stale_over_365d"], STALE_DAYS, inventory["broken_links"]))
    print("  %-9s: %d findings" % ("drift", len(report["drift"])))
    drift_stat = scan_stats["drift"]
    dropped = sum(drift_stat["discarded"].values())
    if drift_stat["found"] > drift_stat["emitted"] or dropped:
        print("  %-9s: %d of %d findings shown, %d of %d path candidates dropped by the gates"
              % ("filtered", drift_stat["emitted"], drift_stat["found"], dropped,
                 drift_stat["candidates"]))
    if scan_stats["ignore_unchecked"]:
        print("  %-9s: %s, %d paths guessed at because %s"
              % ("ignored", scan_stats["ignore_source"], scan_stats["ignore_unchecked"],
                 scan_stats["ignore_fallback"]))

    present = [item["id"] for item in report["signals"] if item["state"] == "present"]
    hints = [item["id"] for item in report["signals"] if item["state"] == "hint"]
    if present:
        print("\npresent signals (%d)" % len(present))
        print("  " + ", ".join(present))
    if hints:
        print("\nhints, never verdict-setting (%d)" % len(hints))
        print("  " + ", ".join(hints))
    if report["drift"]:
        print("\ndrift, most specific first")
        for row in report["drift"][:12]:
            where = "%s:%s" % (row["doc"], row["line"]) if row.get("line") else row["doc"]
            print("  %-9s: %s -> %s" % (row["kind"][:9], where, row["detail"]))
        if len(report["drift"]) > 12:
            print("  %-9s: %d more" % ("...", len(report["drift"]) - 12))
    if report["unknown"]:
        print("\nnot looked at, or refused")
        for row in report["unknown"]:
            print("  %-9s: %s" % (row["family"], row["reason"]))
    print("\nI only see documentation committed to this repo.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan a repository for documentation signals, "
                                                 "inventory, and drift.")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--family", action="append", choices=FAMILIES,
                        help="limit gated passes and output to this signal family")
    parser.add_argument("--deep", action="store_true", help="run pass 3 per-document git metrics")
    parser.add_argument("--exclude-dir", action="append",
                        help="keep a directory out of the document inventory and drift pass")
    parser.add_argument("--max-evidence", type=int, default=MAX_EVIDENCE,
                        help="evidence records kept per signal")
    args = parser.parse_args(argv)

    try:
        report = scan(args.repo, set(args.family or []), args.deep, max(1, args.max_evidence),
                      args.exclude_dir)
    except (OSError, ValueError) as error:
        sys.stderr.write("docdna_scan: %s\n" % error)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
