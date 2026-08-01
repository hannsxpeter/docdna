#!/usr/bin/env python3
"""Collect merged commits between two refs and group them for release notes."""

import argparse
import json
import subprocess
import sys

TOOL = "collect_commits"
VERSION = "0.4.0"
TYPES = ("feat", "fix", "perf", "docs", "refactor", "test", "build", "ci", "chore")


def run_git(root, args):
    process = subprocess.run(["git", "-C", root] + args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    if process.returncode != 0:
        return None
    return process.stdout.decode("utf-8", "replace")


def classify(subject):
    head = subject.split(":", 1)[0].strip().lower()
    for kind in TYPES:
        if head == kind or head.startswith(kind + "("):
            return kind
    return "other"


def collect(root, since):
    span = "%s..HEAD" % since if since else "HEAD"
    text = run_git(root, ["log", "--no-merges", "--pretty=%H\t%s", span]) or ""
    groups = {}
    for line in text.splitlines():
        if "\t" not in line:
            continue
        sha, subject = line.split("\t", 1)
        groups.setdefault(classify(subject), []).append({"sha": sha[:12], "subject": subject})
    return {"tool": TOOL, "version": VERSION, "since": since, "groups": groups}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect commits for release notes.")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--since", help="the previous tag")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(argv)

    report = collect(args.repo, args.since)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for kind in sorted(report["groups"]):
            print("%s: %d" % (kind, len(report["groups"][kind])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
