# Development setup template

Catalog id `build.dev-setup`. Default path `docs/build/dev-setup.md`. Producible Y. GAP prefix `DEV`.

Normative. This file is an instruction set, not prose to copy. **No sentence below may appear in the
document.** Every line the document carries is derived from a file in this repository at the recorded
commit, or it is a GAP marker.

## Skeleton, in this order

1. The frontmatter block, filled from the write plan's `frontmatter` object. Fields the plan leaves null
   stay null. See `_frontmatter.md`.
2. The reconstruction banner, verbatim from the write plan's `banner` string. See `_banner.md`.
3. A single `#` heading naming this repository's own artifact, taken from the `name` key of its package
   manifest and cited. If no manifest declares a name, the heading is the repository directory name and
   carries no claim.
4. The sections below, in order. Omit a section whose evidence is absent unless its GAP severity is
   `blocker`.
5. The document control block. See `_document-control.md`.

## Rules that outrank every section below

- Every paragraph, bullet, and table row carries a citation or a GAP marker. There is no third state.
- **A command that no file declares is not a command.** If `npm run dev`, `make serve`, or
  `python manage.py runserver` does not appear as a script, a target, an entry point, or a CI step, it is a
  `human-input` GAP. Inventing a plausible command is the single most common way this document goes
  wrong, and it is the failure the drift detector was built to catch.
- **No number is generated.** Not a port, a version, a timeout, a memory limit, a worker count, or a
  duration. Every number is copied from the file that sets it and cited to that file, or it is a
  `human-input` GAP.
- Substitution test: if a sentence stays true after swapping this project for a different one in a
  different language, delete it.
- **An exhaustive or negative claim is a claim about a search, not about a symbol.** "These are all the
  prerequisites", "no other command is needed", and "nothing else must be set locally" are carried by a
  `run` citation holding the command and its output, or they are narrowed to the named set actually
  inspected, or they are an `unverifiable` GAP. A `code` citation resolves one symbol in one file and
  cannot support either shape. Prefer the narrowed form here: this document is read by someone following
  it, and "the files below are what the repository declares" is both true and useful, where "that is
  everything you need" is neither provable nor, usually, true. See `references/evidence.md`.

## `## Prerequisites`

**Evidence.** Version pins only: `.nvmrc`, `.python-version`, `.tool-versions`, `.ruby-version`, the
`engines` key of `package.json`, `requires-python` in `pyproject.toml`, the `rust-version` key of
`Cargo.toml`, the `go` directive in `go.mod`, the `FROM` line of each Dockerfile, the image or
`setup-*` action version in each CI job.

**Write.** One table row per pinned tool: tool, version, and the file that pins it. Cite each row with a
`code` citation to that file plus a verbatim anchor.

**Absent.** No pin anywhere is a finding, not a blank: emit
`kind=human-input sev=major asks="Which runtime versions are supported, and where should that be
pinned so it stops being tribal knowledge?"`

**Numbers.** A version string is copied character for character from the pinning file. Never widen
`3.11.4` to `3.11+` and never infer a version from a dependency's release history.

## `## Get the code and install dependencies`

**Evidence.** The lockfile present in the tree decides the package manager: `package-lock.json`,
`pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`, `poetry.lock`, `uv.lock`, `Pipfile.lock`, `Cargo.lock`,
`go.sum`, `Gemfile.lock`. The install step in each CI job is the second source and outranks inference,
because CI is the one place the install is known to work.

**Write.** The clone command, then the install command, each cited to the lockfile or the CI step that
proves it. If CI and the lockfile disagree, document the CI command and record the disagreement as a
bullet with both citations.

**Absent.** No lockfile and no CI install step:
`kind=human-input sev=blocker asks="Which package manager installs this project's dependencies?"`

**Numbers.** None belong in this section.

## `## Configure the environment`

**Evidence.** `.env.example`, `.env.sample`, `.env.template`, the settings module named in the write
plan's covers, and any CI `env:` block.

**Write.** Only the variables that must be set before the process starts. Name the variable, say which
file reads it, and cite the read site. Do not restate the full configuration surface; link to the
configuration reference if the manifest selected one.

**Never.** No secret value, no example token, no connection string with credentials, not even the
placeholder from `.env.example`. Name the key and stop.

**Absent.** The process reads environment variables and no example file exists:
`kind=human-input sev=major asks="Which environment variables must be set locally, and what is a safe
value for each?"`

## `## Run it`

**Evidence.** Declared entry points only: the `scripts` block of `package.json`, targets in `Makefile` or
`justfile` or `Taskfile.yml`, `project.scripts` in `pyproject.toml`, `[[bin]]` in `Cargo.toml`, `Procfile`
lines, the `command`entry of a compose service, the `CMD` or `ENTRYPOINT` of a Dockerfile.

**Write.** One bullet per runnable command, in the order a newcomer needs them, each cited to its
declaration site. State what the command starts and where it listens only if a file says so.

**Absent.** Nothing declares a runnable entry point:
`kind=not-implemented sev=major asks="Is this project runnable as a service, or is it a library with no
start command?"` A library with no start command is a fact, not a hole, and saying so is the useful
answer.

**Numbers.** A port number is cited to the file that binds it. If the port comes from an environment
variable, say what the read site does about a default and cite that call: "`os.getenv("PORT")` is called
with no fallback" is a `code` claim about one expression. "There is no default anywhere in the tree" is a
different, larger claim and needs a `run` citation or an `unverifiable` GAP.

## `## Run the tests`

**Evidence.** The test command in CI, the test runner config (`pytest.ini`, `jest.config.*`,
`vitest.config.*`, `go.mod` plus `_test.go` files, `Cargo.toml` plus `tests/`), and the declared test
script.

**Write.** The command CI runs, cited to the workflow step. Then any narrower command the config makes
possible, cited to the config.

**Numbers.** A test count is only ever a `run` citation with the command that produced it, for example
``[run: `python3 -m pytest --collect-only -q` -> 214 tests]``. Never state a count you did not capture,
and never state coverage as a percentage unless a committed report states it.

**Absent.** No test configuration in the tree:
`kind=not-implemented sev=major asks="Are there automated tests for this project, and where do they
run?"`

## `## When setup fails`

**Evidence.** Only the failures the repository already knows about: a troubleshooting section in an
existing document, a `continue-on-error` or retry in CI, a pinned dependency with an explanatory comment,
a platform guard in a build script.

**Write.** One bullet per known failure with its fix, each cited. If the repository knows about no
failures, the section is absent. Do not stock it with generic advice.

**Absent.** Omit the section entirely. A troubleshooting section made of guesses sends a newcomer down a
path nobody has walked.

## `## What this document does not cover`

**Evidence.** The write plan's `covers` list, and the manifest rows for adjacent documents.

**Write.** One bullet per adjacent concern that lives elsewhere, naming the document and its path.
Deployment, configuration reference, and architecture are separate documents. Say where they are, or say
they do not exist yet and cite the manifest row.

## Refuse to write

- If no manifest, lockfile, Makefile, CI workflow, or Dockerfile exists, there is no evidence for this
  document. Report the absence and write no file.
- If cited claim blocks come out fewer than GAP markers, this is a request for information wearing a
  heading. Record `status: not-started` with the blockers and create no file.
