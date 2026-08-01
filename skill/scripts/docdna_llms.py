#!/usr/bin/env python3
"""Emit llms.txt, the agent-readable index of the documents this repository actually has."""

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timezone

SCHEMA = 1
TOOL = "docdna_llms"
VERSION = "1.0.1"

HERE = os.path.dirname(os.path.abspath(__file__))
SELECT_SCRIPT = os.path.join(HERE, "docdna_select.py")

MANIFEST_REL = os.path.join(".docdna", "manifest.json")
META_REL = os.path.join(".docdna", "meta")
OUTPUT_REL = "llms.txt"
OUTPUT_ID = "build.llms-txt"
OUTPUT_TITLE = "Agent documentation index"
REPORT_REL = "DOCDNA.md"

STAGES = ("frame", "decide", "design", "build", "verify", "assure", "operate", "serve",
          "govern", "retire")
STAGE_TITLES = {
    "frame": "Frame: why this exists, for whom, and what counts as success",
    "decide": "Decide: what was chosen, and what was rejected",
    "design": "Design: what shape it is, and why that shape",
    "build": "Build: how to work on it",
    "verify": "Verify: how we know it works",
    "assure": "Assure: how it is shown to be safe, lawful, and accessible",
    "operate": "Operate: how it is run and kept alive",
    "serve": "Serve: how someone uses it",
    "govern": "Govern: how the work itself is managed",
    "retire": "Retire: how it ends",
}

PRESENT_STATES = ("present-fresh", "present-drifted", "present-stub")
STATE_NOTES = {"present-drifted": "Stale: at least one claim in it is contradicted by the code.",
               "present-stub": "Stub: under 400 bytes, so treat it as a placeholder."}

PROSE_EXT = (".md", ".markdown", ".rst", ".adoc", ".txt")
SKIP_PREFIX = ("#", ">", "|", "<!--", "---", "===", "```", "![", "_Confidence")
SKIP_BULLET = ("- ", "* ", "+ ", "1. ")
EMPHASIS = ("**", "__", "*", "_", "`")
LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")

SUMMARY_LIMIT = 180
LINE_WIDTH = 100
MAX_DIR_FILES = 500
VOWELS = "aeiou"

PRECEDENCE = ("If a document below contradicts the code, the code is correct and the document is "
              "stale; say so rather than repeating it.")


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def run_select(repo):
    command = [sys.executable, SELECT_SCRIPT, "--unattended", repo]
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 0:
        raise ValueError("docdna_select.py failed: %s"
                         % process.stderr.decode("utf-8", "replace").strip())


def read_manifest(root):
    path = os.path.join(root, MANIFEST_REL)
    if not os.path.exists(path):
        run_select(root)
    if not os.path.exists(path):
        raise ValueError("no %s under %s, and docdna_select.py wrote none"
                         % (MANIFEST_REL, root))
    manifest = load_json(path)
    if manifest.get("schema") != SCHEMA:
        raise ValueError("%s declares schema %s, this build reads schema %d"
                         % (MANIFEST_REL, manifest.get("schema"), SCHEMA))
    return manifest


def strip_frontmatter(lines):
    if not lines or lines[0].strip() != "---":
        return lines
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            return lines[index + 1:]
    return lines


def article(word):
    return "an" if word[:1].lower() in VOWELS else "a"


def plural(count, word, suffix="s"):
    return "%d %s%s" % (count, word, "" if count == 1 else suffix)


def stage_rank(stage):
    return STAGES.index(stage) if stage in STAGES else len(STAGES)


def flatten(text):
    text = LINK.sub(r"\1", text)
    for marker in EMPHASIS:
        text = text.replace(marker, "")
    return text.strip()


def summarize(text):
    text = " ".join(flatten(text).split())
    if len(text) <= SUMMARY_LIMIT:
        return text
    cut = text.rfind(" ", 0, SUMMARY_LIMIT)
    if cut <= 0:
        cut = SUMMARY_LIMIT
    return text[:cut].rstrip(" ,;:") + "..."


def first_paragraph(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return ""
    for raw in strip_frontmatter(lines):
        line = raw.strip()
        if not line or line.startswith(SKIP_PREFIX) or line.startswith(SKIP_BULLET):
            continue
        return summarize(line)
    return ""


def count_files(path):
    total = 0
    for _, _, names in os.walk(path):
        for name in names:
            if not name.startswith("."):
                total += 1
        if total > MAX_DIR_FILES:
            break
    return total


def summary_for(full):
    if os.path.isdir(full):
        count = count_files(full)
        if count > MAX_DIR_FILES:
            return "over %d files in this directory." % MAX_DIR_FILES
        return "%s in this directory." % plural(count, "file")
    if full.lower().endswith(PROSE_EXT):
        return first_paragraph(full)
    return ""


def describe(entry):
    parts = []
    summary = entry["summary"]
    if summary:
        parts.append(summary if summary.endswith((".", "!", "?")) else summary + ".")
    note = STATE_NOTES.get(entry["state"])
    if note and entry["kind"] == "file":
        parts.append(note)
    if entry["also"]:
        parts.append("Also indexed as %s." % ", ".join(entry["also"]))
    return " ".join(parts)


def entry_path(root, row):
    path = row.get("path") or ""
    found = row.get("found_at")
    if path.endswith("/"):
        if os.path.isdir(os.path.join(root, path)):
            return path
        parent = os.path.dirname(found or "")
        if parent and os.path.isdir(os.path.join(root, parent)):
            return parent + "/"
    return found or path


def collect(root, manifest):
    skipped = {"not_present": 0, "elsewhere": 0, "missing_file": 0, "self": 0, "duplicate_path": 0}
    rows = []
    for row in manifest.get("documents") or []:
        state = row.get("state")
        if state == "present-elsewhere":
            skipped["elsewhere"] += 1
            continue
        if state not in PRESENT_STATES:
            skipped["not_present"] += 1
            continue
        rel = entry_path(root, row)
        if not rel or os.path.normpath(rel) == OUTPUT_REL:
            skipped["self"] += 1
            continue
        full = os.path.join(root, rel)
        if not os.path.exists(full):
            skipped["missing_file"] += 1
            continue
        rows.append({"id": row["id"], "title": row["title"], "stage": row["stage"], "state": state,
                     "path": rel.replace(os.sep, "/"), "summary": summary_for(full), "also": [],
                     "kind": "directory" if os.path.isdir(full) else "file"})
    rows.sort(key=lambda item: (stage_rank(item["stage"]), item["title"], item["id"]))
    sections = {}
    first_at = {}
    for entry in rows:
        primary = first_at.get(entry["path"])
        if primary is not None:
            primary["also"].append(entry["title"])
            skipped["duplicate_path"] += 1
            continue
        first_at[entry["path"]] = entry
        sections.setdefault(entry["stage"], []).append(entry)
    for entry in first_at.values():
        entry["description"] = describe(entry)
    return sections, skipped


def blockquote(root, manifest, listed):
    name = os.path.basename(os.path.abspath(root))
    primary = (manifest.get("archetype") or {}).get("primary") or "unknown"
    shape = "" if primary == "unknown" else ", %s %s repository" % (article(primary), primary)
    head = manifest.get("repo_head")
    text = ("Documentation index for %s%s. It lists %s committed to this repository, grouped by "
            "lifecycle stage. Generated by %s from %s%s on %s."
            % (name, shape, plural(listed, "document"), manifest.get("generated_by", TOOL),
               MANIFEST_REL, " at commit %s" % head if head else "",
               manifest.get("generated_at") or "an earlier run"))
    return ["> " + line for line in textwrap.wrap(text, LINE_WIDTH - 2)]


def wrapped_note(text):
    return textwrap.wrap("- " + text, LINE_WIDTH, subsequent_indent="  ")


def notes(skipped):
    rows = wrapped_note("Paths are relative to the repository root.")
    rows.extend(wrapped_note(PRECEDENCE))
    tracked = skipped["not_present"] + skipped["elsewhere"] + skipped["missing_file"]
    if tracked:
        held = ""
        if skipped["elsewhere"]:
            held = ", %d of them held outside this repository" % skipped["elsewhere"]
        subject = "document is" if tracked == 1 else "documents are"
        rows.extend(wrapped_note("%d further %s tracked in the manifest and not present here%s. "
                                 "The full set, including what is deliberately not applicable, is "
                                 "in %s and %s."
                                 % (tracked, subject, held, REPORT_REL, MANIFEST_REL)))
    return rows


def render(root, manifest, sections, skipped):
    listed = sum(len(rows) for rows in sections.values())
    lines = ["# %s" % os.path.basename(os.path.abspath(root)), ""]
    lines.extend(blockquote(root, manifest, listed))
    lines.append("")
    lines.extend(notes(skipped))
    lines.append("")
    if not listed:
        lines.append("No document tracked in the manifest is committed to this repository yet.")
        lines.append("")
        return "\n".join(lines)
    for stage in STAGES:
        rows = sections.get(stage)
        if not rows:
            continue
        lines.append("## %s" % STAGE_TITLES[stage])
        lines.append("")
        for row in rows:
            bullet = "- [%s](%s)" % (row["title"], row["path"])
            if row["description"]:
                bullet += ": %s" % row["description"]
            lines.append(bullet)
        lines.append("")
    return "\n".join(lines)


def write_output(root, text):
    path = os.path.join(root, OUTPUT_REL)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def manifest_row(manifest, ident):
    for key in ("documents", "excluded"):
        for row in manifest.get(key) or []:
            if row.get("id") == ident:
                return row
    return {}


def yaml_scalar(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[%s]" % ", ".join(str(item) for item in value)
    text = str(value)
    return text if text else '""'


def sidecar_fields(manifest, stamp):
    row = manifest_row(manifest, OUTPUT_ID)
    return [("id", OUTPUT_ID),
            ("instance_id", None),
            ("title", row.get("title") or OUTPUT_TITLE),
            ("stage", row.get("stage") or "build"),
            ("durability", row.get("durability") or "durable"),
            ("scope", row.get("scope") or "repo"),
            ("system_of_record", row.get("system_of_record") or "repo"),
            ("classification", "unclassified"),
            ("status", "draft"),
            ("owner", "unassigned"),
            ("owner_candidate", row.get("owner_candidate")),
            ("reviewed_by", None),
            ("last_reviewed", stamp),
            ("review_cadence", row.get("cadence") or "on-change"),
            ("next_review", None),
            ("retention", "indefinite"),
            ("valid_until", None),
            ("supersedes", []),
            ("superseded_by", None),
            ("not_applicable_reason", None),
            # llms.txt is rebuilt from .docdna/manifest.json, not from an interface-defining source
            # file, so there is nothing for the drift test to hash. Empty covers is the honest state.
            ("covers", []),
            ("last_validated_commit", manifest.get("repo_head")),
            ("applies_to", None),
            ("satisfies", row.get("satisfies") or ["llmstxt"]),
            ("audiences", row.get("audiences") or ["agents", "users"]),
            ("traces_up", []),
            ("traces_down", []),
            ("derivation", "derived"),
            ("generated_by", "docdna v%s" % VERSION),
            ("generated_on", stamp),
            ("open_questions", [])]


def write_sidecar(root, manifest):
    directory = os.path.join(root, META_REL)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    path = os.path.join(directory, OUTPUT_ID + ".yml")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = ["---"]
    for key, value in sidecar_fields(manifest, stamp):
        lines.append("%s: %s" % (key, yaml_scalar(value)))
    lines.append("---")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def selected_state(manifest):
    for row in manifest.get("documents") or []:
        if row.get("id") == OUTPUT_ID:
            return {"selected": True, "verdict": row.get("verdict"), "because": row.get("because")}
    for row in manifest.get("excluded") or []:
        if row.get("id") == OUTPUT_ID:
            return {"selected": False, "verdict": "not-applicable",
                    "because": [row.get("because")] if row.get("because") else []}
    return {"selected": False, "verdict": None, "because": []}


def build(repo):
    root = os.path.abspath(repo)
    manifest = read_manifest(root)
    sections, skipped = collect(root, manifest)
    text = render(root, manifest, sections, skipped)
    path = write_output(root, text)
    sidecar = write_sidecar(root, manifest)
    documents = []
    for stage in STAGES:
        documents.extend(sections.get(stage) or [])
    return {"schema": SCHEMA, "tool": TOOL, "version": VERSION, "generated": now_utc(),
            "root": root, "path": path, "sidecar": sidecar, "listed": len(documents),
            "skipped": skipped, "profile": selected_state(manifest),
            "sections": [{"stage": stage, "title": STAGE_TITLES[stage],
                          "count": len(sections[stage])}
                         for stage in STAGES if stage in sections],
            "documents": documents}


def print_text(report):
    print("docdna llms %s" % VERSION)
    print("  %-9s: %s" % ("root", report["root"]))
    print("  %-9s: %s" % ("wrote", os.path.relpath(report["path"], report["root"])))
    print("  %-9s: %s" % ("sidecar", os.path.relpath(report["sidecar"], report["root"])))
    print("  %-9s: %s in %s"
          % ("listed", plural(report["listed"], "document"),
             plural(len(report["sections"]), "section")))
    skipped = report["skipped"]
    print("  %-9s: %d tracked and not present, %d held elsewhere, %d path gone"
          % ("omitted", skipped["not_present"], skipped["elsewhere"], skipped["missing_file"]))
    for row in report["sections"]:
        print("  %-9s: %d" % (row["stage"], row["count"]))
    if not report["profile"]["selected"]:
        print("\nNothing in this profile requires %s, so docdna_check.py will report it as an "
              "orphan." % OUTPUT_REL)
        for reason in report["profile"]["because"]:
            print("  %s" % reason)
    print("\nI only index documentation committed to this repo.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Emit llms.txt, the agent-readable index of the "
                                                 "documents this repository actually has.")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(argv)

    try:
        report = build(args.repo)
    except KeyError as error:
        sys.stderr.write("docdna_llms: manifest is missing key %s\n" % error)
        return 2
    except (OSError, ValueError) as error:
        sys.stderr.write("docdna_llms: %s\n" % error)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
