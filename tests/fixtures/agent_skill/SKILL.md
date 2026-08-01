---
name: release-notes
description: Draft release notes for a repository from its merged pull requests and tags. Use when the user asks for release notes, a changelog entry, or a summary of what shipped since the last tag.
allowed-tools: Read, Glob, Grep, Bash
---

# Release notes

Version: 0.4.0

## What this is

A packaged skill that turns merge history into release notes. It reads tags and merged pull
requests, groups them, and drafts a section per group. It writes nothing outside `CHANGELOG.md`.

## Usage

```sh
python3 "<skill-dir>/scripts/collect_commits.py" --since v0.3.0 <target-dir>
```

Resolve `<skill-dir>` to the directory holding this `SKILL.md`.

## Rules

1. Never invent a version number. Read it from the tag.
2. Never claim a change fixed an issue unless the merge message names the issue.
3. Group by the conventional-commit type when every commit carries one, and by directory otherwise.

## Reference files

| File | When |
| --- | --- |
| `references/style.md` | Every run, before drafting |
