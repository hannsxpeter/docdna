# Agent support

<!-- Implements: P-MUST-05 -->

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

Install membership, display labels, full default locations, and wiring surfaces come from
`skill/catalog/runtimes.json`. Both `install.sh` and `docdna_wire.py` validate and consume that registry
through `docdna_runtime.py`; they do not maintain a second host metadata inventory. The shell retains only
the selector-specific environment override adapter names listed in the table above. Each wiring surface
declares its closed renderer kind and path list; validation enforces the renderer's path cardinality, and
wiring preflights every selected destination before any write. A declared install or writable instruction
surface proves only that local operation. Every host row records host parity as not verified.

After installation, run:

```sh
python3 <skill-dir>/scripts/docdna_doctor.py --json
```

Doctor is read-only. Exit code 0 means all registered checks passed, 1 means a required resource or check
failed, and 2 means invalid or unsafe input prevented a verdict. Recovery is to reinstall trusted
`v1.4.0` bytes and rerun Doctor from the installed directory. Installed proof validation checks registry
structure only. Source-checkout evidence, golden replay, and host execution are separate boundaries.

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

## Installing without the shell script

`install.sh` is a POSIX shell convenience, not part of the Python runtime. On a supported POSIX host that
cannot run it, copy the complete `skill/` directory to one of the install targets above. Survey then runs
`docdna_select.py`, which invokes `docdna_scan.py` with the active Python interpreter and writes the same
manifest and report as a shell-installed copy. Wiring can be done by running `docdna_wire.py` or by adding
the block above by hand.

## Agent handoff support

`docdna_status.py --json <repo>` reads the bounded manifest without writing and returns exactly one next
action. When its lane is `agent-ready`, the reported `docdna_backfill.py --only <id> --json <repo>` command
contains a fresh-context packet. The packet binds one document, its evidence and templates, protected
prose, proof limits, output, and verify argv. A packet reports host execution as unknown until the host
reports it; creating a packet is not evidence that an agent spawned or succeeded. If the manifest is
absent, Backfill first runs Survey and writes the manifest and report, so only status inspection itself is
unconditionally read-only.
