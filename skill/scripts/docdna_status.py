#!/usr/bin/env python3
"""Report one next DocDNA action through bounded, read-only manifest inspection."""

# Implements: P-MUST-04, P-MUST-05

import argparse
import json
import os
import shlex
import sys


SCHEMA = 1
TOOL = "docdna_status"
VERSION = "1.4.0"
MAX_STATUS_BYTES = 1024 * 1024
MANIFEST_REL = os.path.join(".docdna", "manifest.json")
WRITE_STATUS = ("pending", "in-progress", "written", "verified", "failed")
SENSITIVE = ("internal", "restricted")
SENSITIVITY = ("public", "internal", "restricted")
ROW_STATUS = ("not-started", "refused")
VERDICT_PRIORITY = {"required": 0, "recommended": 1, "optional": 2}

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from docdna_fs import (bind_root as safe_bind_root,
                       control_file_exists as safe_control_file_exists,
                       parse_json as safe_parse_json,
                       read_text as safe_read_text,
                       require_manifest as safe_require_manifest)


def command_for(script, args, root):
    return ["python3", os.path.join(HERE, script)] + list(args) + [str(root)]


def render_argv(argv):
    if not isinstance(argv, list) or not argv or any(not isinstance(value, str) for value in argv):
        raise ValueError("command argv must be a non-empty array of strings")
    if any(any(ord(character) < 32 or 0x7f <= ord(character) <= 0x9f
               for character in value) for value in argv):
        raise ValueError("command argv contains unsupported control characters")
    return " ".join(shlex.quote(value) for value in argv)


def repository_relative(path):
    if not isinstance(path, str) or not path:
        raise ValueError("manifest document path must be repository-relative: %s" % path)
    if any(ord(character) < 32 or 0x7f <= ord(character) <= 0x9f for character in path):
        raise ValueError("manifest document path contains unsupported control characters")
    if os.path.isabs(path) or "\\" in path:
        raise ValueError("manifest document path must be repository-relative: %s" % path)
    directory = path.endswith("/")
    candidate = path[:-1] if directory else path
    if (not candidate
            or any(part in ("", ".", "..") for part in candidate.split("/"))):
        raise ValueError("manifest document path must be repository-relative: %s" % path)
    normalized = os.path.normpath(candidate).replace(os.sep, "/")
    if normalized in ("", ".") or normalized.startswith("../") or ".." in normalized.split("/"):
        raise ValueError("manifest document path leaves the repository: %s" % path)
    return normalized + "/" if directory else normalized


def action(action_id, lane, label, reason, argv=None):
    if argv is not None:
        argv = list(argv)
    return {"id": action_id, "lane": lane, "label": label,
            "reason": reason, "argv": argv,
            "command": render_argv(argv) if argv is not None else None}


def _identifier(row, fallback):
    for key in ("id", "answer", "question", "doc"):
        value = row.get(key) if isinstance(row, dict) else None
        if isinstance(value, str) and value:
            return value
    return fallback


def firing_tripwires(manifest):
    rows = []
    declared = manifest.get("tripwires")
    if declared is not None:
        if not isinstance(declared, dict) or not isinstance(declared.get("firing", []), list):
            raise ValueError("manifest tripwires must contain a firing array")
        for index, row in enumerate(declared.get("firing") or []):
            if not isinstance(row, dict):
                raise ValueError("manifest tripwires firing[%d] must be an object" % index)
            if not isinstance(row.get("id"), str) or not row["id"]:
                raise ValueError("manifest tripwires firing[%d] id must be a non-empty string"
                                 % index)
            rows.append(row)
    for row in manifest.get("drift") or []:
        if row.get("kind") == "tripwire" or row.get("status") == "firing":
            rows.append(row)
    unique = {}
    for index, row in enumerate(rows):
        ident = _identifier(row, "row-%d" % index)
        unique[ident] = row
    return [(ident, unique[ident]) for ident in sorted(unique)]


def validate_ranked_rows(manifest, field, text_field):
    rows = []
    for index, row in enumerate(manifest.get(field) or []):
        answer = row.get("answer")
        impact = row.get("becomes_required")
        text = row.get(text_field)
        if not isinstance(answer, str) or not answer:
            raise ValueError("manifest %s[%d] answer must be a non-empty string" % (field, index))
        if type(impact) is not int or impact < 0:
            raise ValueError("manifest %s[%d] becomes_required must be a non-negative integer"
                             % (field, index))
        if not isinstance(text, str) or not text:
            raise ValueError("manifest %s[%d] %s must be a non-empty string"
                             % (field, index, text_field))
        copied = dict(row)
        copied["_manifest_index"] = index
        rows.append(copied)
    return sorted(rows, key=lambda row: (-row["becomes_required"], row["_manifest_index"]))


def validate_documents(manifest):
    rows = []
    for index, row in enumerate(manifest.get("documents") or []):
        status = row.get("write_status", "pending")
        if status not in WRITE_STATUS:
            raise ValueError("manifest document %s has invalid write_status %s"
                             % (row.get("id", index), status))
        row_status = row.get("status")
        if row_status is not None and row_status not in ROW_STATUS:
            raise ValueError("manifest document %s has invalid status %s"
                             % (row.get("id", index), row_status))
        sensitivity = row.get("sensitivity")
        if sensitivity not in SENSITIVITY:
            raise ValueError("manifest document %s has invalid sensitivity %s"
                             % (row.get("id", index), sensitivity))
        verdict = row.get("verdict")
        if verdict not in VERDICT_PRIORITY:
            raise ValueError("manifest document %s has invalid verdict %s"
                             % (row.get("id", index), verdict))
        blockers = row.get("blockers")
        if (blockers is not None
                and (not isinstance(blockers, list)
                     or any(not isinstance(item, str) or not item for item in blockers))):
            raise ValueError("manifest document %s blockers must be an array of non-empty strings"
                             % row.get("id", index))
        copied = dict(row)
        copied["write_status"] = status
        copied["_manifest_index"] = index
        if copied.get("path") is not None:
            copied["path"] = repository_relative(copied["path"])
        rows.append(copied)
    return rows


def ranked_documents(rows):
    return sorted(rows, key=lambda row: (VERDICT_PRIORITY[row["verdict"]],
                                         row["_manifest_index"]))


def select_next_action(root, manifest):
    """Choose one stable action without executing it or changing the repository."""
    tripwires = firing_tripwires(manifest)
    questions = validate_ranked_rows(manifest, "open_questions", "prompt")
    assumptions = validate_ranked_rows(manifest, "assumptions", "counterfactual")
    documents = ranked_documents(validate_documents(manifest))
    if tripwires:
        ident, _ = tripwires[0]
        return action("tripwire:%s" % ident, "manual-gated", "Resolve firing tripwire",
                      "Repository state now contradicts an earlier exclusion. Review it before "
                      "local helper work.",
                      command_for("docdna_select.py", [], root))

    if questions:
        ident = _identifier(questions[0], "question")
        return action("question:%s" % ident, "manual-gated", "Answer open survey question",
                      questions[0]["prompt"],
                      command_for("docdna_select.py", [], root))

    if assumptions:
        ident = _identifier(assumptions[0], "assumption")
        reason = assumptions[0].get("counterfactual") or "Confirm or replace the survey fallback."
        return action("assumption:%s" % ident, "manual-gated", "Resolve survey assumption",
                      reason, command_for("docdna_select.py", [], root))

    refused = [row for row in documents
               if row.get("status") in ("refused", "not-started")
               and (row.get("blockers") or row["write_status"] == "failed")]
    if refused:
        row = refused[0]
        reason = (row.get("blockers") or ["The document is explicitly refused."])[0]
        return action("refusal:%s" % row["id"], "manual-gated", "Resolve refusal",
                      reason, None)

    sensitive = [row for row in documents
                 if row.get("sensitivity") in SENSITIVE
                 and row["write_status"] in ("pending", "failed")]
    if sensitive:
        row = sensitive[0]
        return action("sensitive:%s" % row["id"], "manual-gated",
                      "Confirm sensitive document scope",
                      "A human must confirm the repository is not public before packet creation.",
                      command_for("docdna_backfill.py",
                                  ["--only", row["id"], "--confirm-sensitive", "--json"], root))

    verify = []
    for row in documents:
        if row["write_status"] not in ("written", "in-progress") or not row.get("path"):
            continue
        if safe_control_file_exists(root, row["path"]):
            verify.append(row)
    if verify:
        row = verify[0]
        return action("verify:%s" % row["id"], "local-helper", "Verify written document",
                      "Written or in-progress output must be verified before another packet.",
                      command_for("docdna_backfill.py", ["--verify", row["path"]], root))

    pending = [row for row in documents if row["write_status"] != "verified"
               and row.get("status") != "refused"]
    if pending:
        row = pending[0]
        return action("packet:%s" % row["id"], "agent-ready", "Create fresh-context packet",
                      "This is the highest-priority incomplete document that has no manual gate.",
                      command_for("docdna_backfill.py", ["--only", row["id"], "--json"], root))

    return action("check", "read-only", "Check verified documentation",
                  "No incomplete manifest row remains. Inspect current documentation drift.",
                  command_for("docdna_check.py", [], root))


def summary_for(manifest):
    if manifest is None:
        return {"manifest": "absent", "documents": 0, "assumptions": 0,
                "open_questions": 0, "tripwires": 0,
                "write_status": dict((status, 0) for status in WRITE_STATUS)}
    documents = validate_documents(manifest)
    counts = dict((status, 0) for status in WRITE_STATUS)
    for row in documents:
        counts[row["write_status"]] += 1
    return {"manifest": "present", "documents": len(documents),
            "assumptions": len(manifest.get("assumptions") or []),
            "open_questions": len(manifest.get("open_questions") or []),
            "tripwires": len(firing_tripwires(manifest)), "write_status": counts}


def inspect_status(repo):
    root = safe_bind_root(os.path.abspath(repo))
    try:
        if not safe_control_file_exists(root, MANIFEST_REL):
            next_action = action("survey", "read-only", "Survey repository",
                                 "No manifest exists. Survey is the next read-only step.",
                                 command_for("docdna_scan.py", ["--json"], root))
            return {"schema": SCHEMA, "tool": TOOL, "version": VERSION, "mode": "status",
                    "root": str(root), "read_only": True, "summary": summary_for(None),
                    "next_action": next_action}
        text = safe_read_text(root, MANIFEST_REL, max_bytes=MAX_STATUS_BYTES)
        manifest = safe_parse_json(text, MANIFEST_REL)
        safe_require_manifest(manifest, MANIFEST_REL, SCHEMA)
        report = {"schema": SCHEMA, "tool": TOOL, "version": VERSION, "mode": "status",
                  "root": str(root), "read_only": True, "summary": summary_for(manifest)}
        report["next_action"] = select_next_action(root, manifest)
        return report
    finally:
        root.close()


def print_status(report):
    summary = report["summary"]
    action_row = report["next_action"]
    print("docdna status %s" % VERSION)
    print("  %-15s: true" % "read only")
    print("  %-15s: %s" % ("manifest", summary["manifest"]))
    print("  %-15s: %d" % ("documents", summary["documents"]))
    print("  %-15s: %s" % ("one next action", action_row["label"]))
    print("  %-15s: %s" % ("lane", action_row["lane"]))
    print("  %-15s: %s" % ("reason", action_row["reason"]))
    print("  %-15s: %s" % ("command", action_row["command"] or "manual input required"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Report one next DocDNA action without changing the repository."
    )
    parser.add_argument("--json", action="store_true", help="emit stable JSON")
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args(argv)
    try:
        report = inspect_status(args.repo)
    except (OSError, UnicodeError, ValueError) as error:
        sys.stderr.write("docdna_status: %s\n" % error)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_status(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
