#!/usr/bin/env python3
"""Wire DOCDNA.md into registered coding-agent instruction files."""

# Implements: P-MUST-05

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from docdna_fs import (MAX_CONTROL_BYTES, bind_root as safe_bind_root,
                       control_file_exists as safe_control_file_exists,
                       is_dir as safe_is_dir,
                       open_root as safe_open_root,
                       path_exists as safe_path_exists,
                       read_text as safe_read_text, write_text as safe_write_text)
from docdna_runtime import RuntimeRegistryError, load_registry, wiring_target_ids

VERSION = "1.4.0"

START = "<!-- docdna:start -->"
END = "<!-- docdna:end -->"

# Any tool's block delimiter, not just ours. A span that contains one of these is not a span we are
# allowed to overwrite, because the content between another tool's markers belongs to that tool.
MARKER = re.compile(r"<!--\s*[A-Za-z0-9_.-]+:(?:start|end)\s*-->")

PLAIN_BLOCK = """<!-- docdna:start -->
## Project documentation

The documentation set for this repo is indexed in [DOCDNA.md](DOCDNA.md): which documents exist, who owns them, when they were last verified against the code, and what is deliberately not applicable. Agent-readable index at [llms.txt](llms.txt). Before answering questions about how this system works, prefer a document listed there over inference. If a document contradicts the code, the code is correct and the document is stale; say so.
<!-- docdna:end -->
"""

CURSOR_FRONTMATTER = """---
description: Use the docdna documentation index for this repository.
alwaysApply: true
---

"""

CASCADE_FRONTMATTER = """---
trigger: always_on
---

"""

SKILL_ROOT = os.path.normpath(os.path.join(HERE, ".."))
WIRING_SURFACES = {}
ALL_TARGETS = ()


def load_wiring_surfaces(skill_root=SKILL_ROOT):
    """Load the validated registry without running at module import time."""
    registry = load_registry(skill_root)
    surfaces = dict((row["id"], row) for row in registry["wiring_surfaces"])
    global WIRING_SURFACES, ALL_TARGETS
    WIRING_SURFACES = surfaces
    ALL_TARGETS = tuple(wiring_target_ids(registry))
    return surfaces


def foreign_markers(span, start_marker, end_marker):
    for hit in MARKER.finditer(span):
        if hit.group(0) not in (start_marker, end_marker):
            return True
    return False


def locate_block(text, start_marker, end_marker):
    # Two independent find() calls define the span as [first start, first end], which is not
    # necessarily one block. With a duplicated start marker, or a block that has come to wrap a
    # sibling tool's block after a bad merge, that span reaches across another tool's content and
    # replacing it deletes that content outright. So: anchor the end search after the start,
    # re-anchor on a nested start rather than spanning it, and refuse any span holding a marker
    # that is not ours.
    pos = 0
    while True:
        start = text.find(start_marker, pos)
        if start == -1:
            return -1, -1, "absent"
        after = start + len(start_marker)
        end = text.find(end_marker, after)
        if end == -1:
            return -1, -1, "absent"
        nested = text.find(start_marker, after)
        if nested != -1 and nested < end:
            pos = nested
            continue
        if foreign_markers(text[after:end], start_marker, end_marker):
            return start, end + len(end_marker), "conflict"
        return start, end + len(end_marker), "found"


def replace_block(text, block, start_marker, end_marker):
    start, end, status = locate_block(text, start_marker, end_marker)
    if status == "conflict":
        return text
    if status == "found":
        head = text[:start].rstrip()
        joiner = "\n\n" if head else ""
        updated = head + joiner + block.rstrip() + "\n" + text[end:].lstrip()
        return updated.rstrip() + "\n"
    if text.strip():
        return text.rstrip() + "\n\n" + block
    return block


def preflight_write_target(root, path, body, prefix="", start_marker=START, end_marker=END):
    rel = os.path.relpath(str(path), str(root))
    existed = safe_control_file_exists(root, rel)
    text = safe_read_text(root, rel, max_bytes=MAX_CONTROL_BYTES) if existed else ""
    if existed and locate_block(text, start_marker, end_marker)[2] == "conflict":
        return {"path": path, "relative": rel, "updated": None, "action": "skipped"}
    if not text.strip() and prefix:
        updated = prefix + body
    else:
        updated = replace_block(text, body, start_marker, end_marker)
        if not existed and prefix:
            updated = prefix + updated
    return {"path": path, "relative": rel, "updated": updated,
            "action": "updated" if existed else "created"}


def apply_write_target(root, plan):
    if plan["updated"] is None:
        return plan["action"]
    descriptor = safe_open_root(root)
    try:
        safe_write_text(root, plan["relative"], plan["updated"], root_descriptor=descriptor)
    finally:
        os.close(descriptor)
    return plan["action"]


def write_target(root, path, body, prefix="", start_marker=START, end_marker=END):
    plan = preflight_write_target(root, path, body, prefix, start_marker, end_marker)
    return apply_write_target(root, plan)


def rule_path(root, paths):
    root_path = Path(str(root))
    primary, alternate = (root_path / path for path in paths)
    primary_parent = os.path.dirname(paths[0])
    alternate_parent = os.path.dirname(paths[1])
    if safe_is_dir(root, alternate_parent) and not safe_is_dir(root, primary_parent):
        return alternate
    return primary


def cascade_path(root, surfaces=None):
    surfaces = surfaces or load_wiring_surfaces()
    candidates = [row for row in surfaces.values() if row["renderer"] == "cascade-rule"]
    if len(candidates) != 1:
        raise ValueError("registry must declare exactly one cascade-rule wiring surface")
    return rule_path(root, candidates[0]["paths"])


def target_path(root, target, surfaces=None):
    surfaces = surfaces or load_wiring_surfaces()
    surface = surfaces.get(target)
    if surface is None:
        raise ValueError("unknown target: %s" % target)
    renderer = surface["renderer"]
    root_path = Path(str(root))
    if renderer in ("plain-default", "plain-existing"):
        return root_path / surface["paths"][0], "", PLAIN_BLOCK
    if renderer == "cursor-rule":
        return root_path / surface["paths"][0], CURSOR_FRONTMATTER, PLAIN_BLOCK
    if renderer == "cascade-rule":
        return rule_path(root, surface["paths"]), CASCADE_FRONTMATTER, PLAIN_BLOCK
    raise ValueError("unknown wiring renderer: %s" % renderer)


def existing_targets(root, surfaces=None):
    surfaces = surfaces or load_wiring_surfaces()
    targets = []
    for target, surface in surfaces.items():
        renderer = surface["renderer"]
        paths = surface["paths"]
        if renderer == "plain-default":
            targets.append(target)
        elif renderer == "plain-existing" and safe_path_exists(root, paths[0]):
            targets.append(target)
        elif renderer == "cursor-rule" and safe_is_dir(root, os.path.dirname(paths[0])):
            targets.append(target)
        elif renderer == "cascade-rule" and any(
                safe_is_dir(root, os.path.dirname(path)) for path in paths):
            targets.append(target)
    return targets


def wire(root, targets=None, all_targets=False, surfaces=None):
    surfaces = surfaces or load_wiring_surfaces()
    root = safe_bind_root(os.path.abspath(str(root)))
    try:
        return wire_bound(root, targets, all_targets, surfaces)
    finally:
        root.close()


def wire_bound(root, targets=None, all_targets=False, surfaces=None):
    surfaces = surfaces or load_wiring_surfaces()
    selected = list(surfaces if all_targets else (targets or existing_targets(root, surfaces)))
    seen = set()
    plans = []
    for target in selected:
        if target in seen:
            continue
        seen.add(target)
        path, prefix, body = target_path(root, target, surfaces)
        plan = preflight_write_target(root, path, body, prefix, START, END)
        plan["target"] = target
        plans.append(plan)
    results = []
    for plan in plans:
        action = apply_write_target(root, plan)
        results.append({"target": plan["target"], "path": str(plan["path"]),
                        "action": action})
    return results


def main(argv=None):
    try:
        surfaces = load_wiring_surfaces()
    except (RuntimeRegistryError, OSError, ValueError) as error:
        sys.stderr.write("docdna_wire: %s\n" % error)
        return 2
    parser = argparse.ArgumentParser(description="Wire DOCDNA.md into agent instruction files.")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--agent", action="append", choices=tuple(surfaces),
                        help="agent target to create or update")
    parser.add_argument("--all", action="store_true", help="create or update every supported target")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    try:
        results = wire(args.repo, targets=args.agent, all_targets=args.all, surfaces=surfaces)
    except (OSError, ValueError) as error:
        sys.stderr.write("docdna_wire: %s\n" % error)
        return 2
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for item in results:
            print("%s %s: %s" % (item["action"], item["target"], item["path"]))
            if item["action"] == "skipped":
                print("  the docdna block there encloses another tool's block, so replacing it would")
                print("  delete that tool's content. Separate the two blocks by hand and re-run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
