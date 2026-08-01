#!/usr/bin/env python3
"""Scan a repository for documentation signals, existing documents, and drift."""

import argparse
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone

SCHEMA = 1
TOOL = "docdna_scan"
VERSION = "1.0.1"

HERE = os.path.dirname(os.path.abspath(__file__))
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
               "dlx", "list", "ls", "run"}
NPM_RUN = re.compile(r"^(npm|pnpm|yarn|bun)\s+(?:run\s+)?([A-Za-z0-9:_.@-]+)")
MAKE_RUN = re.compile(r"^make\s+(?:-[A-Za-z]\s+)?([A-Za-z0-9:_.-]+)")
MAKE_TARGET = re.compile(r"^([A-Za-z0-9][A-Za-z0-9:_.\-/]*)\s*:(?!=)")
PIP_INSTALL = re.compile(r"^(?:python[\d.]*\s+-m\s+)?pip[\d.]*\s+install\b")
PIP_EDITABLE = re.compile(r"(?:^|\s)(?:-e|--editable)[=\s]+[\"']?\.(?:\[[^\]\s]*\])?[\"']?(?:\s|$)")
BUILD_SYSTEM = re.compile(r"(?m)^\s*\[build-system\]")
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
    command = ["git", "-C", root] + args
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace")


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
    facts["tags"] = len([line for line in (tags or "").splitlines() if line.strip()])
    last = run_git(root, ["log", "-1", "--format=%aI"])
    if last and last.strip():
        facts["last_commit"] = iso_z(last.strip())
        facts["last_commit_days"] = days_since(last.strip())
    cutoff = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    count = run_git(root, ["rev-list", "--count", "--since=" + cutoff, "HEAD"])
    if count and count.strip().isdigit():
        facts["commits_window"] = int(count.strip())
    emails = run_git(root, ["log", "--since=" + cutoff, "--format=%aE"])
    if emails is not None:
        facts["authors_window"] = len(set(line.strip().lower() for line in emails.splitlines()
                                          if line.strip()))
    facts["authors"] = git_shortlog(root)
    collect_git_paths(root, facts)
    return facts


def git_shortlog(root):
    text = run_git(root, ["shortlog", "-sne", "HEAD"])
    authors = []
    for line in (text or "").splitlines():
        match = re.match(r"^\s*(\d+)\s+(.*?)\s+<([^>]*)>\s*$", line)
        if match:
            authors.append({"name": match.group(2), "commits": int(match.group(1)),
                            "email": match.group(3).lower(), "last": None})
    return authors


def collect_git_paths(root, facts):
    text = run_git(root, ["log", "-n", str(MAX_LOG_COMMITS), "--name-only",
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
    files = []
    pruned = set()
    for base, dirs, names in os.walk(root):
        keep = []
        for name in dirs:
            if prune_dir(name, base):
                pruned.add(name)
            else:
                keep.append(name)
        dirs[:] = sorted(keep)
        for name in names:
            files.append(os.path.relpath(os.path.join(base, name), root).replace(os.sep, "/"))
    return sorted(files), pruned


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
    if denied_read(rel):
        ctx["cache"][rel] = None
        return None
    if scan["files_read"] >= MAX_READ_FILES:
        scan["files_capped"] += 1
        scan["truncated"] = True
    else:
        full = os.path.join(ctx["root"], rel)
        try:
            if os.path.getsize(full) > MAX_FILE_BYTES:
                scan["files_skipped_large"] += 1
            else:
                with open(full, encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
                scan["files_read"] += 1
        except OSError:
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
        if resolve_path(ctx, base, cleaned) is None:
            broken += 1
    return total, broken


def resolve_path(ctx, base, token):
    candidates = [token]
    if base:
        candidates.append(os.path.normpath(os.path.join(base, token)).replace(os.sep, "/"))
    for candidate in candidates:
        candidate = candidate.rstrip("/")
        if candidate in ctx["pathset"] or candidate in ctx["dirs"]:
            return candidate
    return None


def normalize_excludes(values):
    out = set()
    for value in values or []:
        cleaned = value.strip().replace(os.sep, "/").strip("/")
        if cleaned.startswith("./"):
            cleaned = cleaned[2:].strip("/")
        if cleaned:
            out.add(cleaned)
    return out


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
    try:
        return os.path.getsize(os.path.join(ctx["root"], rel))
    except OSError:
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
        entry = {"dir": folder, "path": rel, "build_system": False, "packaged": False,
                 "names": set(), "entries": set()}
        surface["python"][folder] = entry
    return entry


def command_surface(ctx):
    surface = {"scripts": {}, "scripts_path": None, "targets": set(), "makefile": None,
               "ci": "", "python": {}, "cargo_path": None, "cargo_bins": set(), "go_mod": None,
               "process_path": None, "process_cmd": None}
    for rel in ctx["paths"]:
        base = os.path.basename(rel)
        if base == "package.json" and surface["scripts_path"] is None:
            text = read_text(ctx, rel)
            flat = manifest_flat(rel, text or "")
            scripts = flat.get("scripts")
            if isinstance(scripts, dict):
                surface["scripts"] = dict(scripts)
                surface["scripts_path"] = rel
        elif base in ("Makefile", "makefile", "GNUmakefile") and surface["makefile"] is None:
            text = read_text(ctx, rel) or ""
            surface["makefile"] = rel
            for line in text.splitlines():
                match = MAKE_TARGET.match(line)
                if match and match.group(1) not in (".PHONY", ".DEFAULT"):
                    surface["targets"].update(match.group(1).split())
        elif base == "pyproject.toml":
            text = read_text(ctx, rel) or ""
            flat = flatten_toml(text)
            entry = python_manifest(surface, rel)
            entry["path"] = rel
            entry["build_system"] = BUILD_SYSTEM.search(text) is not None
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


def nearest_manifest(entries, doc):
    if not entries:
        return None
    base = os.path.dirname(doc)
    best = None
    for entry in entries:
        folder = entry["dir"]
        if folder and not (base == folder or base.startswith(folder + "/")):
            continue
        if best is None or len(folder) > len(best["dir"]):
            best = entry
    if best is None and len(entries) == 1:
        best = entries[0]
    return best


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
    if not match or not surface["scripts_path"]:
        return None
    name = match.group(2)
    if match.group(1) == "npm" and "run" not in command.split()[:2]:
        return None
    if name.startswith("-") or name in PM_BUILTINS or name in surface["scripts"]:
        return None
    if name in surface["ci"] or command in surface["ci"]:
        return None
    known = ", ".join(sorted(surface["scripts"])[:6]) or "none"
    return drift_row(doc, "command-not-found", command, surface["scripts_path"] + ":scripts",
                     "no `%s` script; scripts are %s" % (name, known), "high", number,
                     (commit_day(ctx, doc), commit_day(ctx, surface["scripts_path"])))


def make_drift(ctx, doc, number, command, surface):
    match = MAKE_RUN.match(command)
    if not match or not surface["makefile"]:
        return None
    name = match.group(1)
    if name in surface["targets"] or name in surface["ci"]:
        return None
    known = ", ".join(sorted(surface["targets"])[:6]) or "none"
    return drift_row(doc, "command-not-found", command, surface["makefile"] + ":targets",
                     "no `%s` target; targets are %s" % (name, known), "high", number,
                     (commit_day(ctx, doc), commit_day(ctx, surface["makefile"])))


def editable_drift(ctx, doc, number, command, entry):
    if entry is None or entry["build_system"] or entry["packaged"]:
        return None
    where = entry["path"]
    return drift_row(
        doc, "command-not-found", command, where + ":build-system",
        "%s has no [build-system] table and there is no setup.py or setup.cfg, so an editable "
        "install fails on a clean machine" % where, "high", number,
        (commit_day(ctx, doc), commit_day(ctx, where)))


def manage_drift(ctx, doc, number, command, surface, name):
    if name not in MANAGE_SERVE or not surface["process_cmd"]:
        return None
    return drift_row(
        doc, "command-not-found", command, surface["process_path"] + ":process command",
        "%s runs %s, not `manage.py %s`" % (surface["process_path"], surface["process_cmd"], name),
        "high", number, (commit_day(ctx, doc), commit_day(ctx, surface["process_path"])))


def script_drift(ctx, doc, number, command, entry):
    if entry is None or not entry["names"]:
        return None
    name = command.split()[0]
    if dep_name(name) not in entry["names"]:
        return None
    if dep_name(name) in set(dep_name(item) for item in entry["entries"]):
        return None
    where = entry["path"]
    known = ", ".join(sorted(entry["entries"])[:6]) or "none"
    confidence = "medium" if entry["packaged"] else "high"
    return drift_row(
        doc, "command-not-found", command, where + ":project.scripts",
        "no console script named `%s` is declared; declared scripts are %s" % (name, known),
        confidence, number, (commit_day(ctx, doc), commit_day(ctx, where)))


def python_drift(ctx, doc, number, command, surface):
    match = MANAGE_RUN.match(command)
    if match:
        return manage_drift(ctx, doc, number, command, surface, match.group(1))
    entry = nearest_manifest(sorted(surface["python"].values(), key=lambda item: item["dir"]), doc)
    if PIP_INSTALL.match(command) and PIP_EDITABLE.search(command):
        return editable_drift(ctx, doc, number, command, entry)
    return script_drift(ctx, doc, number, command, entry)


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
        "no crate named `%s` in any Cargo.toml; declared names start %s" % (name, known),
        "high", number, (commit_day(ctx, doc), commit_day(ctx, surface["cargo_path"])))


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
        "no `%s` package in the repository" % target, "high", number,
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
    text = token.strip().strip(",.;:")
    if ")" in text and "(" not in text:
        text = text.rstrip(")")
    text = re.sub(r":[\d,\-]+$", "", text)
    if not text or " " in text or len(text) > 120:
        return None
    if text.startswith(("http", "mailto:", "#", "@", "-", "<", "$", "/", "~", "!")):
        return None
    for bad in ("://", "*", "?", "<", ">", "{", "}", "$", "|", "..", "\\"):
        if bad in text:
            return None
    if text.startswith("./"):
        text = text[2:]
    text = text.rstrip("/")
    if not text:
        return None
    extension = os.path.splitext(text)[1].lower()
    if "/" not in text and extension not in TEXT_EXT | DOC_EXT:
        return None
    if "/" not in text and not extension:
        return None
    return text


def output_path(candidate):
    for prefix in OUTPUT_PREFIXES:
        if candidate == prefix or candidate.startswith(prefix + "/"):
            return True
    return False


def check_paths(ctx, doc, text):
    rows = []
    base = os.path.dirname(doc)
    seen = set()
    for number, token, source in path_tokens(text):
        candidate = path_candidate(token)
        if candidate is None or candidate in seen:
            continue
        seen.add(candidate)
        if resolve_path(ctx, base, candidate) is not None:
            continue
        if output_path(candidate):
            continue
        if os.path.basename(candidate) in ctx["basenames"]:
            continue
        parent = os.path.dirname(candidate)
        first = candidate.split("/")[0]
        if not parent:
            if source != "link":
                continue
            confidence = "high"
        elif parent in ctx["dirs"]:
            confidence = "high"
        elif first in ctx["dirs"]:
            confidence = "medium"
        else:
            continue
        rows.append(drift_row(doc, "path-not-found", candidate, "file index",
                              "no such file or directory in the repository", confidence, number))
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


def check_counts(ctx, doc, text, routes, routes_path):
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
                "%d routes detected" % routes, "medium", number,
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


def build_drift(ctx, docs):
    surface = command_surface(ctx)
    routes, routes_path = openapi_routes(ctx)
    if not routes:
        http = ctx["results"].get("iface.http") or {}
        if http.get("state") == "present":
            routes = http["hits"]
            routes_path = (http["evidence"][0]["path"] if http.get("evidence") else "iface.http")
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
        rows.extend(check_counts(ctx, rel, text, routes, routes_path))
        lag = ctx["doc_lag"].get(rel)
        if lag and lag["days"] > LAG_DAYS:
            rows.append(drift_row(
                rel, "stale-vs-code", "documents %s" % lag["code_path"], lag["code_path"],
                "code changed %d days after the document was last touched" % lag["days"],
                "high" if lag["days"] > STALE_DAYS else "medium", None,
                (lag["doc_date"], lag["code_date"])))
    rows.sort(key=lambda row: (row["doc"], row.get("line") or 0, row["kind"]))
    if len(rows) > MAX_DRIFT:
        ctx["scan"]["truncated"] = True
    return rows[:MAX_DRIFT]


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
    root = os.path.abspath(root)
    index = build_index(root)
    denied = [rel for rel in index["paths"] if denied_read(rel)]
    excludes = normalize_excludes(excludes)
    ctx = {"root": root, "paths": index["paths"], "pathset": index["pathset"],
           "dirs": index["dirs"], "entries": index["entries"], "basenames": index["basenames"],
           "cache": {}, "results": {}, "docs": [], "doc_lag": {}, "deep": deep,
           "excludes": excludes, "git": collect_git(root),
           "scan": {"files_total": len(index["paths"]), "files_read": 0, "files_skipped_large": 0,
                    "files_denied": len(denied), "files_capped": 0, "read_errors": 0,
                    "dirs_pruned": index["pruned"], "dirs_excluded": sorted(excludes),
                    "index_source": index["source"],
                    "max_file_bytes": MAX_FILE_BYTES, "truncated": False}}
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
    emitted = [results[sig["id"]] for sig in sorted(signals, key=lambda item: item["id"])
               if sig["id"] in results and (not families or sig["family"] in families)]
    for doc in inventory["docs"]:
        doc.pop("top_author", None)
    return {"schema": SCHEMA, "tool": TOOL, "version": VERSION, "generated": now_utc(),
            "root": root, "commit": ctx["git"]["head"], "dirty": ctx["git"]["dirty"],
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
    print("  %-9s: %d indexed, %d read, %d denied, %d unreadable"
          % ("files", scan_stats["files_total"], scan_stats["files_read"],
             scan_stats["files_denied"], scan_stats["read_errors"]))
    print("  %-9s: %d present, %d hint, %d absent, %d unknown"
          % ("signals", counts["present"], counts["hint"], counts["absent"], counts["unknown"]))
    print("  %-9s: %d markdown, %d opaque, %d with frontmatter"
          % ("docs", inventory["total"], inventory["opaque"], inventory["with_frontmatter"]))
    print("  %-9s: %d over %d days, %d broken links"
          % ("stale", inventory["stale_over_365d"], STALE_DAYS, inventory["broken_links"]))
    print("  %-9s: %d findings" % ("drift", len(report["drift"])))

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

    report = scan(args.repo, set(args.family or []), args.deep, max(1, args.max_evidence),
                  args.exclude_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)


if __name__ == "__main__":
    main()
