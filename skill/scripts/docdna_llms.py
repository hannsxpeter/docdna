#!/usr/bin/env python3
"""Emit llms.txt, the agent-readable index of the documents this repository actually has."""

import argparse
import json
import os
import re
import sys
import textwrap
from urllib.parse import quote

SCHEMA = 1
TOOL = "docdna_llms"
VERSION = "1.4.0"

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from docdna_fs import run_select
from docdna_fs import (MANIFEST_STAGES, MAX_CONTROL_BYTES, bind_root as safe_bind_root,
                       denied_read, is_dir as safe_is_dir,
                       is_file as safe_is_file,
                       listdir as safe_listdir, load_json, now_utc, output_path,
                       path_exists as safe_exists, parse_json as safe_parse_json, plural,
                       read_text as safe_read_text, repository_path,
                       require_manifest as safe_require_manifest,
                       run_in_root as safe_run_in_root, today, write_repository_text)
from docdna_unicode import clean_generated_text

DOCUMENTS_PATH = os.path.normpath(os.path.join(HERE, "..", "catalog", "documents.json"))

MANIFEST_REL = os.path.join(".docdna", "manifest.json")
META_REL = os.path.join(".docdna", "meta")
OUTPUT_REL = "llms.txt"
OUTPUT_ID = "build.llms-txt"
OUTPUT_TITLE = "Agent documentation index"
REPORT_REL = "DOCDNA.md"

STAGES = MANIFEST_STAGES
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
# present-drifted is earned by a single low-confidence lead, so the note may not say the code
# contradicts the document. Adjudication put the two passes behind that state at 3.2 and 10.9
# percent precision, which means most rows carrying this note are a document naming a path or a
# command for a reason other than asserting it is here right now. Describe the lead, not a verdict.
STATE_NOTES = {"present-drifted": ("Lead: at least one path or command in it did not resolve "
                                   "against the code, at low confidence and for a human to read."),
               "present-stub": "Stub: under 400 bytes, so treat it as a placeholder."}

LINE_WIDTH = 100
MAX_DIR_FILES = 500

PRECEDENCE = ("If a document below contradicts the code, the code is correct and the document is "
              "stale; say so rather than repeating it.")


def tracked_paths(root):
    process = safe_run_in_root(root, ["git", "ls-files", "-z", "--cached"], 60)
    if process is None or process.returncode != 0:
        return None
    return set(item for item in process.stdout.decode("utf-8", "replace").split("\0") if item)


def repository_name(root):
    # The origin name survives a renamed checkout, unlike the local directory name.
    fallback = os.path.basename(os.path.abspath(root))
    process = safe_run_in_root(root, ["git", "config", "--get", "remote.origin.url"], 10)
    if process is None or process.returncode != 0:
        return fallback
    remote = process.stdout.decode("utf-8", "replace").strip()
    name = os.path.basename(os.path.normpath(remote))
    if name.endswith(".git"):
        name = name[:-4]
    if re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", name):
        return name
    return fallback


def indexed_path(paths, rel):
    if paths is None:
        return True
    cleaned = rel.replace(os.sep, "/").strip("/")
    prefix = cleaned + "/" if cleaned else ""
    return cleaned in paths or any(item.startswith(prefix) for item in paths)


def readable_repository_path(root, candidate, paths):
    full = repository_path(root, candidate)
    if full is None:
        return None
    root_real = os.path.realpath(root)
    target = os.path.realpath(full)
    source_rel = os.path.relpath(full, os.path.abspath(root)).replace(os.sep, "/")
    target_rel = os.path.relpath(target, root_real).replace(os.sep, "/")
    if denied_read(source_rel) or denied_read(target_rel):
        return None
    if not indexed_path(paths, source_rel) or not indexed_path(paths, target_rel):
        return None
    return target


def read_repository_text(root, rel, max_bytes=None):
    output_path(root, rel)
    return safe_read_text(root, rel, max_bytes=max_bytes)


def read_manifest(root):
    output_path(root, MANIFEST_REL)
    if not safe_exists(root, MANIFEST_REL):
        run_select(root)
    if not safe_exists(root, MANIFEST_REL):
        raise ValueError("no %s under %s, and docdna_select.py wrote none"
                         % (MANIFEST_REL, root))
    text = read_repository_text(root, MANIFEST_REL, max_bytes=MAX_CONTROL_BYTES)
    manifest = safe_parse_json(text, MANIFEST_REL)
    return safe_require_manifest(manifest, MANIFEST_REL, SCHEMA)


def stage_rank(stage):
    return STAGES.index(stage) if stage in STAGES else len(STAGES)


def count_files(root, path, paths):
    total = 0
    pending = [path]
    visited = set()
    while pending:
        folder = readable_repository_path(root, pending.pop(), paths)
        if folder is None:
            continue
        real = os.path.realpath(folder)
        if real in visited:
            continue
        visited.add(real)
        try:
            names = safe_listdir(root, folder)
        except (OSError, ValueError):
            continue
        for name in names:
            child_source = os.path.join(folder, name)
            child = readable_repository_path(root, child_source, paths)
            if child is None:
                continue
            if safe_is_dir(root, child):
                if not os.path.islink(child_source):
                    pending.append(child)
            elif safe_is_file(root, child) and not name.startswith("."):
                total += 1
        if total > MAX_DIR_FILES:
            break
    return total


def summary_for(root, full, paths):
    if safe_is_dir(root, full):
        count = count_files(root, full, paths)
        if count > MAX_DIR_FILES:
            return "over %d files in this directory." % MAX_DIR_FILES
        return "%s in this directory." % plural(count, "file")
    return ""


def trusted_documents():
    rows = load_json(DOCUMENTS_PATH)["documents"]
    return dict((row["id"], {"title": row["title"], "stage": row["stage"]}) for row in rows)


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
        full = repository_path(root, path)
        target = os.path.realpath(full) if full is not None else None
        if target is not None and safe_is_dir(root, target):
            return path
        parent = os.path.dirname(found or "")
        full = repository_path(root, parent) if parent else None
        target = os.path.realpath(full) if full is not None else None
        if target is not None and safe_is_dir(root, target):
            return parent + "/"
    return found or path


def collect(root, manifest):
    skipped = {"not_present": 0, "elsewhere": 0, "missing_file": 0, "self": 0, "duplicate_path": 0}
    rows = []
    paths = tracked_paths(root)
    catalog = trusted_documents()
    for row in manifest.get("documents") or []:
        state = row.get("state")
        if state == "present-elsewhere":
            skipped["elsewhere"] += 1
            continue
        if state not in PRESENT_STATES:
            skipped["not_present"] += 1
            continue
        trusted = catalog.get(row["id"])
        if trusted is None:
            skipped["not_present"] += 1
            continue
        rel = entry_path(root, row)
        if not rel or os.path.normpath(rel) == OUTPUT_REL:
            skipped["self"] += 1
            continue
        full = readable_repository_path(root, rel, paths)
        if full is None or not safe_exists(root, full):
            skipped["missing_file"] += 1
            continue
        rows.append({"id": row["id"], "title": trusted["title"],
                     "stage": trusted["stage"], "state": state,
                     "path": rel.replace(os.sep, "/"),
                     "summary": summary_for(root, full, paths), "also": [],
                     "kind": "directory" if safe_is_dir(root, full) else "file"})
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


def blockquote(root, listed, name=None):
    name = name or repository_name(root)
    text = ("Documentation index for %s. It lists %s committed to this repository, grouped by "
            "lifecycle stage. Generated by docdna v%s from %s."
            % (name, plural(listed, "document"), VERSION, MANIFEST_REL))
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


def render(root, sections, skipped):
    listed = sum(len(rows) for rows in sections.values())
    name = repository_name(root)
    lines = ["# %s" % name, ""]
    lines.extend(blockquote(root, listed, name))
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
            target = quote(row["path"], safe="/._~-")
            bullet = "- [%s](%s)" % (row["title"], target)
            if row["description"]:
                bullet += ": %s" % row["description"]
            lines.append(bullet)
        lines.append("")
    return "\n".join(lines)


def write_output(root, text):
    clean_text, _stats = clean_generated_text(text)
    return write_repository_text(root, OUTPUT_REL, clean_text)


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
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


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
    output_path(root, META_REL)
    stamp = today()
    lines = ["---"]
    for key, value in sidecar_fields(manifest, stamp):
        lines.append("%s: %s" % (key, yaml_scalar(value)))
    lines.append("---")
    clean_text, _stats = clean_generated_text("\n".join(lines) + "\n")
    return write_repository_text(root, os.path.join(META_REL, OUTPUT_ID + ".yml"), clean_text)


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
    root = safe_bind_root(os.path.abspath(repo))
    try:
        return build_bound(root)
    finally:
        root.close()


def build_bound(root):
    manifest = read_manifest(root)
    sections, skipped = collect(root, manifest)
    text = render(root, sections, skipped)
    path = write_output(root, text)
    sidecar = write_sidecar(root, manifest)
    documents = []
    for stage in STAGES:
        documents.extend(sections.get(stage) or [])
    return {"schema": SCHEMA, "tool": TOOL, "version": VERSION, "generated": now_utc(),
            "root": str(root), "path": path, "sidecar": sidecar, "listed": len(documents),
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
