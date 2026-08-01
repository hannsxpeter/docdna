#!/usr/bin/env python3
"""Wire DOCDNA.md into common coding-agent instruction files."""

import argparse
import json
from pathlib import Path

START = "<!-- docdna:start -->"
END = "<!-- docdna:end -->"

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

PLAIN_TARGETS = {
    "agents": Path("AGENTS.md"),
    "claude": Path("CLAUDE.md"),
    "gemini": Path("GEMINI.md"),
    "copilot": Path(".github/copilot-instructions.md"),
}

ALL_TARGETS = ["agents", "claude", "gemini", "copilot", "cursor", "cascade"]

RULE_BASENAME = "docdna"


def replace_block(text, block, start_marker, end_marker):
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start != -1 and end != -1 and start < end:
        end += len(end_marker)
        head = text[:start].rstrip()
        joiner = "\n\n" if head else ""
        updated = head + joiner + block.rstrip() + "\n" + text[end:].lstrip()
        return updated.rstrip() + "\n"
    if text.strip():
        return text.rstrip() + "\n\n" + block
    return block


def write_target(path, body, prefix="", start_marker=START, end_marker=END):
    existed = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if existed else ""
    if not text.strip() and prefix:
        updated = prefix + body
    else:
        updated = replace_block(text, body, start_marker, end_marker)
        if not existed and prefix:
            updated = prefix + updated
    path.write_text(updated, encoding="utf-8")
    return "updated" if existed else "created"


def cascade_path(root):
    devin = root / ".devin/rules"
    windsurf = root / ".windsurf/rules"
    if windsurf.exists() and not devin.exists():
        return windsurf / (RULE_BASENAME + ".md")
    return devin / (RULE_BASENAME + ".md")


def target_path(root, target):
    if target in PLAIN_TARGETS:
        return root / PLAIN_TARGETS[target], "", PLAIN_BLOCK
    if target == "cursor":
        return root / (".cursor/rules/" + RULE_BASENAME + ".mdc"), CURSOR_FRONTMATTER, PLAIN_BLOCK
    if target == "cascade":
        return cascade_path(root), CASCADE_FRONTMATTER, PLAIN_BLOCK
    raise ValueError("unknown target: %s" % target)


def existing_targets(root):
    targets = ["agents"]
    for name, rel in PLAIN_TARGETS.items():
        if name != "agents" and (root / rel).exists():
            targets.append(name)
    if (root / ".cursor/rules").exists():
        targets.append("cursor")
    if (root / ".devin/rules").exists() or (root / ".windsurf/rules").exists():
        targets.append("cascade")
    return targets


def wire(root, targets=None, all_targets=False):
    root = Path(root)
    selected = list(ALL_TARGETS if all_targets else (targets or existing_targets(root)))
    seen = set()
    results = []
    for target in selected:
        if target in seen:
            continue
        seen.add(target)
        path, prefix, body = target_path(root, target)
        action = write_target(path, body, prefix, START, END)
        results.append({"target": target, "path": str(path), "action": action})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Wire DOCDNA.md into agent instruction files.")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--agent", action="append", choices=ALL_TARGETS, help="agent target to create or update")
    parser.add_argument("--all", action="store_true", help="create or update every supported target")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    results = wire(args.repo, targets=args.agent, all_targets=args.all)
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for item in results:
            print("%s %s: %s" % (item["action"], item["target"], item["path"]))


if __name__ == "__main__":
    main()
