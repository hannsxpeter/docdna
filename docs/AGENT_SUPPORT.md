# Agent support

Where docdna installs, what it wires, and the facts about agent context files that it depends on.

Verified 2026-07-31. Host behaviour changes; confirm against your host's current docs before relying on a
row below.

## Install targets

`./install.sh <all|claude|codex|cursor|windsurf>` copies the whole `skill/` directory, because docdna needs
its `catalog/`, `references/`, and `templates/` beside `SKILL.md`, not just the entrypoint.

| Host | Destination | Override |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/docdna/` | `CLAUDE_SKILLS_DIR` |
| Codex | `~/.codex/skills/docdna/` | `CODEX_SKILLS_DIR`, or `CODEX_HOME` |
| Cursor | `~/.cursor/skills/docdna/` | `CURSOR_SKILLS_DIR` |
| Windsurf and Cascade | `~/.codeium/windsurf/skills/docdna/` | `WINDSURF_SKILLS_DIR` |

**A skill is a directory containing `SKILL.md`, never a bare `.md` file.** A file at
`~/.claude/skills/docdna.md` is not loaded, and nothing errors when it is there: the skill simply never
appears. The installer removes a stale bare-file install if it finds one.

Restart the host after installing. Skill listings are read at startup.

## Project wiring

`docdna_wire.py` adds an idempotent block pointing agents at `DOCDNA.md`.

```sh
python3 ~/.claude/skills/docdna/scripts/docdna_wire.py /path/to/repo
```

By default it creates or updates `AGENTS.md` as the portable baseline and updates tool-specific files that
already exist. Pass `--all` to create every supported target, or `--agent <name>` to pick.

| Target | File | Notes |
| --- | --- | --- |
| `agents` | `AGENTS.md` | Always created. The portable baseline. |
| `claude` | `CLAUDE.md` | See below. Wire this explicitly for Claude Code. |
| `gemini` | `GEMINI.md` | |
| `copilot` | `.github/copilot-instructions.md` | |
| `cursor` | `.cursor/rules/docdna.mdc` | Gets `alwaysApply: true` frontmatter |
| `cascade` | `.devin/rules/docdna.md`, or `.windsurf/rules/docdna.md` | Prefers `.windsurf` only when `.devin` is absent. Gets `trigger: always_on` frontmatter. |

### AGENTS.md and CLAUDE.md

`AGENTS.md` is the cross-tool convention. Claude Code's own project-memory file is `CLAUDE.md`, so
**writing only `AGENTS.md` is not sufficient for Claude Code**, and a good deal of widely-circulated advice
gets this backwards.

docdna wires `CLAUDE.md` explicitly rather than relying on inheritance. If you prefer one source of truth,
the supported interop path is an import line in `CLAUDE.md`:

```markdown
@AGENTS.md
```

**Do not use a symlink.** Creating one on Windows requires Administrator or Developer Mode, so a repo that
depends on it breaks for a subset of contributors in a way that is annoying to diagnose.

### If you also use codedna

docdna neither requires codedna nor detects it, and everything above works the same whether it is
installed or not. This section is for the reader who runs both.

The two skills wire the same files, and their blocks are disjoint by construction: different markers
(`<!-- docdna:start -->` against `<!-- codedna:start -->`), different rule basenames, different artifacts.
Both blocks present in one `AGENTS.md` is a fine steady state, and `tests/test_wire.py` has a fixture
asserting that neither clobbers the other.

The guarantee is not specific to that one tool. `docdna_wire.py` threads its start and end markers through
`replace_block` as parameters rather than reading them from module constants, so any foreign block in a
file docdna edits survives, whoever wrote it.

### What the block says, and why the last sentence matters

```markdown
<!-- docdna:start -->
## Project documentation

The documentation set for this repo is indexed in [DOCDNA.md](DOCDNA.md): which documents exist, who owns
them, when they were last verified against the code, and what is deliberately not applicable.
Agent-readable index at [llms.txt](llms.txt). Before answering questions about how this system works,
prefer a document listed there over inference. If a document contradicts the code, the code is correct and
the document is stale; say so.
<!-- docdna:end -->
```

The closing sentence is not decoration. A pointer block that does not state precedence makes stale
documentation authoritative to every agent that reads it, which is worse than having no block at all.

## Degrading without Bash

Only `docdna_scan.py` is required for the Survey happy path. A host that cannot run Bash degrades to a
manual Survey: the agent reads `catalog/documents.json` and evaluates the predicates itself, which is
slower and coarser but produces the same manifest shape. Wiring degrades to editing the instruction files
by hand with the block above.
