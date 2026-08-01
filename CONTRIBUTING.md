# Contributing to docdna

Thanks for your interest in improving docdna. It is a small project with a clear shape, so contributing is straightforward.

## What docdna is

docdna is a portable coding-agent skill installed as a directory for hosts that support `SKILL.md`. The entrypoint lives in [`skill/SKILL.md`](skill/SKILL.md), executable helpers live under [`skill/scripts/`](skill/scripts/), and the machine-readable document catalog lives under [`skill/catalog/`](skill/catalog/). There is no build step and no runtime dependency to install.

docdna stands alone. Python 3.8 is the whole dependency list, and no other tool has to be present for any of it to work. If you also use [codedna](https://github.com/hannsxpeter/codedna), which fingerprints how a repo writes code, treat it as a separate project that happens to install and wire the same way: nothing here imports it, tests against it, or degrades without it.

## The one rule that governs everything

**Nothing is asserted that the repository cannot prove.** Every claim docdna writes carries a citation to a file and a symbol, or a GAP marker saying a human has to supply it. There is no third state. If you are adding a feature that would emit a plausible sentence with nothing behind it, that is the feature to redesign.

Two corollaries worth stating separately, because they are the ones contributors trip over:

- **No number is ever generated.** Not an RTO, an RPO, an SLA, an availability target, a capacity figure, a retention period, or a review cadence. Every one of those is a decision a person owns. Numbers are cited or they are `human-input` GAPs. That rule binds the writer absolutely. The checker that enforces it does not reach everywhere, and the places it stops are named in section 2 of [`skill/references/evidence.md`](skill/references/evidence.md). Keep those two statements distinct in anything you write.
- **An exclusion is a decision, so it carries a reason, a citation, and a tripwire.** A document ruled not-applicable without a `revisit_when` predicate is a guess wearing a decision's clothes.

## Adding a check

**When you add a check, write down what it cannot catch, in the same commit.** An overclaimed check is worse than a missing one. A missing check leaves a reader appropriately unsure; a check described as tighter than it is buys false confidence, and the reader who eventually finds the gap discounts every other guarantee in the project. This tool's entire thesis is that nothing is asserted the repository cannot prove, and that applies first to what the tool asserts about itself.

Three questions to answer before the pull request is ready:

- **What input defeats it?** Write the bypass down even if you are not closing it. `docdna_backfill.py --verify` resolves a `code` anchor and then accepts any number written within `BIND_LINES` lines of it, whether or not the anchor says anything about that number, so a constant sitting beside the cited symbol still certifies a figure nobody decided. That is the honest description, and it belongs next to the check rather than in a reviewer's head.
- **Does it verify, or does it accept an attestation?** Anything the model supplies and the tool re-reads is verification. Anything the model supplies and the tool takes at face value is attestation. A `run:` citation is attestation: docdna never runs the documented repository's own commands, so nothing executes the command and the writer produces both the command and its output. Attestation is legitimate; calling it verification is not.
- **Where does it belong?** A limit that stays inside a docstring or a commit message is not documented. It goes in `skill/references/evidence.md` if a writer needs it while writing, and in the refusal list in `README.md` if it qualifies a promise made to a user.

A check that cannot state its own mesh size is not finished, and "it catches the common case" is only acceptable as prose in the repository, never as an unqualified claim.

## Changing the catalog

[`skill/catalog/SCHEMA.md`](skill/catalog/SCHEMA.md) is normative. Read it before editing any JSON under `skill/catalog/`, and note that `docdna_select.py` enforces its ten invariants as hard errors at load time. A catalog change that violates one fails the build rather than degrading quietly.

Two things to know:

- **Adding a document entry is cheap; adding a template is not.** Naming a document and ruling on it costs one JSON row. Shipping a template invites the model to fill it, so a template is only correct for entries whose content is genuinely derivable from code. That is why the catalog is large and the writing surface is small.
- **Ids are the join key across every file and every user's manifest.** Renaming one is a breaking change. Deprecate and add instead.

If you change an entry count, change `tests/test_catalog.py` in the same commit. That is how the catalog stays a decision instead of a drawer.

## Detection patterns

New signal patterns need a false-positive fixture before they ship. The five patterns in `tests/test_falsepositive.py` are there because earlier versions of them misfired on real code: a security lexicon matched a French locale file, an HTTP route detector matched a client-side router, a personal-data detector matched a weather API's latitude column. Every runtime pattern gets a negative fixture, not just a positive one.

Security lexicons exclude locales, i18n bundles, `.po` files, and lockfiles globally. Jurisdiction signals are capped at `hint` and may open a question but never set a verdict.

## Testing a change

Run the automated checks before opening a pull request:

```sh
python3 -m py_compile skill/scripts/docdna_scan.py
python3 -m py_compile skill/scripts/docdna_select.py
python3 -m py_compile skill/scripts/docdna_backfill.py
python3 -m unittest discover -s tests
tmp="$(mktemp -d)"
CLAUDE_SKILLS_DIR="$tmp/claude" CODEX_SKILLS_DIR="$tmp/codex" CURSOR_SKILLS_DIR="$tmp/cursor" WINDSURF_SKILLS_DIR="$tmp/windsurf" ./install.sh all
```

If `shellcheck` is installed, run `shellcheck install.sh` as well.

Then validate the behavior manually:

1. Install your working copy with one target such as `./install.sh codex`.
2. In a supported coding-agent session, point it at a real repository: "survey the documentation for this repo."
3. Read the generated `DOCDNA.md`. Ask of every line whether it would read differently for a different repository. A line that survives substitution for a competitor's project name and a different stack is not documentation, and it is the most common regression.

To run the scanner on its own:

```sh
python3 skill/scripts/docdna_scan.py --json /path/to/repo
```

## House style

Match what is already there. The Python is stdlib-only, no f-strings, no type hints, no function docstrings, `%` formatting, one module docstring per file, `main(argv=None)`, and an optional `--json` flag emitting `json.dumps(..., indent=2, sort_keys=True)`. The prose is terse and second person.

No em dashes, no en dashes, and no emojis anywhere in the repository.
