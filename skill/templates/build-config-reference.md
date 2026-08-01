# Configuration reference template

Catalog id `build.config-reference`. Default path `docs/build/config-reference.md`. Producible Y. GAP
prefix `CFG`.

Normative. This file is an instruction set, not prose to copy. **No sentence below may appear in the
document.** This document is where invented defaults do the most damage: a wrong default here is copied
into a production environment file by someone who trusts it.

## Skeleton, in this order

1. The frontmatter block from the write plan's `frontmatter` object. See `_frontmatter.md`.
2. The reconstruction banner, verbatim from the write plan's `banner`. See `_banner.md`.
3. A single `#` heading.
4. The sections below, in order.
5. The document control block. See `_document-control.md`.

## Rules that outrank every section below

- Every table row carries a citation to the read site, meaning the line of code or config that consumes
  the setting, not the example file that mentions it.
- **A default is copied or it is absent.** If the read site has no default, the cell says the setting is
  required and cites the read site. Never fill a default cell from what the value usually is.
- **No secret value is ever written.** Not a real one, not a placeholder from `.env.example`, not a
  redacted one. Name the key, name the store it should come from if a file says which, and stop. This
  applies to connection strings, which carry credentials inside a URL.
- **No number is generated.** Ports, pool sizes, timeouts, retry counts, TTLs, batch sizes, and memory
  limits are copied from the file that sets them and cited, or they are `human-input` GAPs.
- **Precedence is a claim.** "Environment variables override the config file" is only true if the loader
  says so. Cite the loader or emit a GAP.
- **An exhaustive or negative claim is a claim about a search, not about a symbol.** "Every declared key
  has a read site", "no other loader exists", and "nothing reloads configuration" are carried by a `run`
  citation holding the command and its output, or they are narrowed to the named set actually inspected,
  or they are an `unverifiable` GAP. A `code` citation resolves one symbol in one file and cannot support
  either shape. See `references/evidence.md`.

## `## Settings`

**Evidence.** The read sites named in the write plan's covers: every `os.environ[...]`, `os.getenv`,
`process.env.X`, `viper.Get`, settings class attribute, `config.get`, or typed settings field. The example
environment file is corroboration, never the primary source, because it goes stale first.

**Write.** One table row per setting, columns: name, type, required, default, read site, what it changes.
Sort alphabetically, because this table is read by lookup and not by narrative. Cite each row to its read
site with a symbol or a verbatim anchor.

**Absent per cell.** The effect of a setting is not visible from its read site:
`kind=unverifiable sev=minor asks="What does <NAME> change? It is read once and passed through."`
No default at the read site and none in the example file:
`kind=human-input sev=major asks="What is the correct value of <NAME> for a new environment?"`

**Numbers.** Every default in this table is a character-for-character copy of the literal at the read
site. If the default is computed, say it is computed and cite the expression.

## `## Settings that are declared and never read`

**Evidence.** Keys present in `.env.example`, a values file, or a settings schema, with no read site
anywhere in the tree.

**Write.** One bullet per orphan key, cited to the file that declares it. "No read site exists" is a
negative claim about the whole tree, so each bullet carries the search that supports it as a `run`
citation, for example ``[run: `grep -rn "LEGACY_CACHE_URL" -- .` -> 1 match, .env.example:14]``. Without
that command, this is a section of guesses about absence, and absence is what it is entirely about. Where
the search cannot be run, say which paths were searched and cite that scope instead. This is the
highest-signal section in the document, a finding a reader cannot get any other way, and it is usually
true, which is exactly why it must be checkable.

**Absent.** "Every declared key has a read site" is a negative universal about the whole tree, so a `code`
citation cannot carry it. Write it only with a `run` citation holding the search that settles it, for
example
``[run: `grep -o '^[A-Z_][A-Z0-9_]*' .env.example | while read k; do grep -rq "$k" src/ || echo "$k"; done` -> no output]``.
If that search is not runnable here, narrow the sentence to the keys you actually traced and name them
("each of the eleven keys in `.env.example` has a read site, cited above"), or emit
`kind=unverifiable sev=minor asks="Is every declared configuration key read somewhere? The tree was not
searched exhaustively."` Do not write the unqualified sentence.

## `## Secrets`

**Evidence.** Read sites whose key names match a credential shape, plus any committed secret-store
configuration: a vault path, a secret manager resource, a sealed secret, a CI secret reference.

**Write.** One row per secret: key, where it is read, and where the environment is expected to source it
from if a committed file says. Nothing else.

**Absent.** No secret store is configured anywhere:
`kind=human-input sev=blocker asks="Where do production secrets come from? Nothing in the repository
names a secret store."`

**Never.** No rotation interval, no expiry date, no key length recommendation. Every one of those is a
policy number a person owns.

## `## Precedence and layering`

**Evidence.** The loader: the order in which sources are merged, the override flags, the environment
selection variable.

**Write.** One ordered list, highest precedence first, cited to the loader symbol that implements the
order. If the loader merges by dictionary update, say which side wins and cite the merge call.

**Absent.** "Configuration comes from one source only" asserts that no second loader exists anywhere, so
it needs a `run` citation naming the search across the tree, for example
``[run: `grep -rn "os.environ\|os.getenv\|load_dotenv\|ConfigParser\|viper.Read" src/ | wc -l` -> 6 sites, all in src/config/settings.py]``.
Without that search, narrow it to what you read ("the only loader in `covers` is `settings.Settings`") and
cite that loader, or emit
`kind=unverifiable sev=minor asks="Does any other component load configuration? Only the files in covers
were read."` A precedence section for a single source is filler either way, so this is one sentence and
not a section.

## `## Differences between environments`

**Evidence.** Committed per-environment files only: a values file per environment, a CI matrix, an
environment block in a deployment descriptor.

**Write.** One row per setting that differs, with the value in each committed environment file, cited to
each file. Omit environments that exist only as names in a pipeline; a name is not a configuration.

**Absent.** Environment names appear in CI but no committed file sets values per environment:
`kind=unverifiable sev=major asks="Where are the per-environment values stored? The pipeline names
environments the repository does not configure."`

## `## Changing a setting`

**Evidence.** Whether the process reads configuration once at start or re-reads it: a reload signal
handler, a watcher, a config server client.

**Write.** One cited sentence on whether a change takes effect without a restart. The positive half is
`code`: the settings object is built once at import in a named symbol, cite it and cite its position in
the start path. **The negative half is not.** "Nothing in the tree implements reloading" needs a `run`
citation naming the search, for example
``[run: `grep -rn "SIGHUP\|watchdog\|fsnotify\|reload" src/` -> no matches]``. Without that search, write
only the positive half and emit
`kind=unverifiable sev=minor asks="Is there a reload path for configuration anywhere in this service? The
tree was not searched for one."`

## Refuse to write

- If the write plan found no read sites, this project has no configuration surface to document. Report
  that and write no file.
- If cited claim blocks come out fewer than GAP markers, record `status: not-started` with the blockers
  and create no file.
