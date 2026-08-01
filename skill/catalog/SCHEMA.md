# Catalog schema

Normative. This is the one schema document. Prose references in `references/` describe intent; where
they disagree with this file, this file wins. `docdna_select.py` enforces every invariant in section 9
as a hard error, not a warning.

## 1. Files

| File | Holds | Read by |
| --- | --- | --- |
| `signals.json` | The signal id registry: families, labels, detection rules, gates | `docdna_scan.py`, `docdna_select.py` |
| `documents.json` | Every catalog entry: id, stage, durability, scope, producible, cadence, path | `docdna_select.py` |
| `rules.json` | The verdict rules, each a predicate plus an effect | `docdna_select.py` |
| `archetypes.json` | Primaries with scoring weights, overlays with triggers, the unknown floor | `docdna_select.py` |
| `interview.json` | The eight questions, their defaults, their counterfactual text | `docdna_select.py` |

All five are JSON, never YAML. stdlib has no `yaml` module and a hand-rolled parser breaks on the first
user who writes a comment or an anchor. Every file is a single top-level object with `schema` and a
payload array, so a version bump is detectable without parsing the payload.

```json
{"schema": 1, "signals": [ ... ]}
```

## 2. Conventions

**Ids are lowercase, dot-separated, and stable.** A signal id is `<family>.<name>`. A document id is
`<stage>.<slug>`. Ids are the join key across all five files and across the manifest. Renaming one is a
breaking change to every user's manifest, so do not rename; deprecate and add.

**Every list is sorted by id** so a diff of a catalog change is readable. `tests/test_catalog.py`
asserts this.

**No prose in the catalog beyond what the report prints.** `label` and `because` templates are user
visible. Rationale belongs in `references/`, not in a JSON comment field nobody renders.

## 3. Signal states

Four values. The fourth is the correction the adversarial pass forced.

| State | Meaning | Satisfies `{"is": "present"}` |
| --- | --- | --- |
| `present` | Detected, with at least one evidence record | yes |
| `absent` | The detector ran and found nothing | no |
| `unknown` | The detector did not run, or refuses to guess | no |
| `hint` | Detected, but too weak to set a verdict | **no** |

`hint` is a distinct state rather than a low-confidence `present` for exactly one reason: so that no rule
can consume it as `present` by accident. Every jurisdiction signal is `hint` at most. A `hint` may open an
interview question. It may never set a verdict, and section 9 enforces that.

**Absence of evidence is never encoded as `false`.** A grep whose gate did not fire reports `unknown`, and
`unknown` never silences a document. This is the difference between "we decided this does not apply" and
"we did not look".

## 4. The predicate grammar

One grammar, used by `documents.json.selects_on`, `rules.json.when`, `archetypes.json.overlays[].when`,
and `manifest.excluded[].revisit_when`. A predicate is a JSON object with exactly one operator key.

### 4.1 Operators

| Form | True when |
| --- | --- |
| `{"all": [P, ...]}` | every child is true. Empty list is true. |
| `{"any": [P, ...]}` | at least one child is true. Empty list is false. |
| `{"not": P}` | the child is false |
| `{"signal": "sec.authn", "is": "present"}` | that signal is in that exact state |
| `{"signal": "data.pii", "gte": 3}` | state is `present` **and** `hits >= 3` |
| `{"answer": "q3_authorizer", "in": ["government-authorizer", "sector-regulator"]}` | the recorded answer is one of these |
| `{"archetype": "oss-library"}` | the resolved primary equals this |
| `{"overlay": "ai-system"}` | this overlay is active |
| `{"document": "decide.adr", "state": "present"}` | inventory says that document exists |
| `{"always": true}` | always |
| `{"never": true}` | never |

`is` accepts one of the four states. `gte` implies `present`, so `{"signal": "x", "gte": 1}` is the
idiomatic "at least one real hit" test and can never be satisfied by a `hint`.

**A missing signal id is a hard error, not a false.** A predicate naming a signal absent from
`signals.json` fails the build. This is what stops a typo from silently excluding a document.

### 4.2 Evaluation

Evaluation is total: every predicate returns `true` or `false`, never `unknown`. The three-valued logic
lives in the state test, not in the combinator, because a tri-state combinator makes `not` ambiguous and
every rule author gets it wrong. If you need "we did not look", test `{"signal": "x", "is": "unknown"}`
explicitly.

### 4.3 The `hint` guardrail

A predicate that reaches `{"is": "hint"}` may only appear in a rule whose effect is `ask` or `note`.
`docdna_select.py` rejects a rule that tests for `hint` and sets a verdict. See invariant I4.

## 5. `signals.json`

```json
{
  "id": "sec.weak_crypto",
  "family": "sec",
  "label": "weak cryptographic primitive in call position",
  "pass": 2,
  "gate": {"any": [{"signal": "sec.crypto", "is": "present"}]},
  "max_state": "present",
  "confidence_cap": "high",
  "detect": {
    "kind": "grep",
    "include_ext": [".py", ".js", ".ts", ".go", ".java", ".rb"],
    "exclude_glob": ["**/locales/**", "**/i18n/**", "*.po", "**/*.lock", "package-lock.json"],
    "patterns": [
      "hashlib\\.md5\\(",
      "crypto\\.createHash\\(['\"]md5",
      "MessageDigest\\.getInstance\\(\"MD5\""
    ]
  },
  "refuses_to_guess": false,
  "question": null
}
```

| Field | Meaning |
| --- | --- |
| `family` | One of the fifteen. Must be the id prefix. |
| `pass` | 1 cheap and always, 2 gated grep, 3 deep and `--deep` only |
| `gate` | Predicate over pass-1 signals. If false, the signal reports `unknown`, never `absent`. |
| `max_state` | Ceiling. `hint` on every `jur.*` signal. The scanner cannot exceed it. |
| `confidence_cap` | Ceiling on reported confidence. `medium` on `data.pii`. |
| `detect.kind` | `path`, `manifest`, `grep`, `git`, or `derived` |
| `exclude_glob` | Applied before matching. Every security lexicon excludes locales and lockfiles. |
| `refuses_to_guess` | When true `detect` is null, the signal is always `unknown`, and `question` names its interview question |

### 5.1 Detector vocabulary

`detect` is null exactly when `refuses_to_guess` is true. Otherwise `kind` selects which keys apply.

| `kind` | Keys | Behaviour |
| --- | --- | --- |
| `path` | `globs`, `files` | Present when any path in the index matches. Reads nothing. |
| `manifest` | `files`, `keys`, `not_keys`, `deps` | Parses a known manifest and tests for keys or declared dependencies. |
| `grep` | `include_ext`, `include_glob`, `exclude_glob`, `exclude_patterns`, `patterns`, `corroborate` | Reads matching files and applies `patterns`. |
| `git` | `metric`, `window_days`, `threshold_days` | Derived from git history. Reports `unknown` outside a git repository. |
| `derived` | `depends_on`, `when`, `match_detail` | Computed from other signals. Never reads a file itself. |

**`corroborate` is the false-positive brake and it is normative.** A grep whose entry carries it fires only
when a second pattern also matches within `scope`.

```json
"corroborate": {"scope": "same_file", "any": ["\\bfrom\\s+fastapi\\b", "http\\.ListenAndServe\\("]}
```

`scope` is `same_file` or `repo`. Without corroboration, `iface.http` fires on a client-side Vue router
and `data.pii` fires on a weather API's `latitude` column. Both were observed. A pattern that needs a
brake and does not have one is a bug, not a tuning preference.

**The fifteen families are a fixed enum**: `arch`, `deploy`, `iface`, `data`, `ai`, `users`, `sec`,
`supply`, `ops`, `qual`, `jur`, `proc`, `docs`, `a11y`, `scale`. Adding a family is a schema bump.

**Every `present` signal carries at least one evidence record.** A `present` with no evidence is a scanner
bug and `docdna_scan.py` raises rather than emitting it.

**`hits` means two different things, and the detector kind decides which.** For `path`, `grep`, and
`manifest` detectors it counts occurrences, so `present` implies `hits >= 1`. For `git` and `derived`
detectors carrying a `metric` it is a measured magnitude, and **zero is a real measurement**: a repository
cloned today reports `proc.last_commit_days` as `present` with `hits` of 0. Requiring a positive value
there would force the scanner either to report `absent` when it did successfully measure, which is exactly
the absence-of-evidence-as-false error section 3 forbids, or to inflate the number. Predicates that need a
threshold use `gte`, which is defined on the magnitude and is therefore correct for both readings.

## 6. `documents.json`

```json
{
  "id": "assure.attack-surface",
  "title": "Attack surface inventory",
  "stage": "assure",
  "durability": "durable",
  "scope": "product",
  "producible": "Y",
  "backfillability": "H",
  "cadence": "P180D",
  "sensitivity": "internal",
  "path": "docs/assure/inputs/attack-surface.md",
  "selects_on": {"any": [
    {"signal": "sec.authn", "is": "present"},
    {"signal": "data.pii", "gte": 1},
    {"signal": "arch.service", "is": "present"}
  ]},
  "baseline_verdict": "recommended",
  "satisfies": ["ssdf:PW.1.1", "iso27001:A.8.27"],
  "audiences": ["engineering", "security"],
  "defers_to": null,
  "detect_paths": ["docs/assure/inputs/attack-surface.md", "docs/security/attack-surface.md"],
  "system_of_record": "repo"
}
```

| Field | Values |
| --- | --- |
| `stage` | `frame` `decide` `design` `build` `verify` `assure` `operate` `serve` `govern` `retire` |
| `durability` | `durable` `evidence` `transient` |
| `scope` | `repo` `product` `org` |
| `producible` | `Y` writes it, `M` manifest-only, `R` refuse |
| `backfillability` | `H` `P` `N` |
| `cadence` | ISO 8601 duration, or `none`, `on-release`, `on-change` |
| `sensitivity` | `public` `internal` `restricted` |
| `defers_to` | Another skill that owns this document, or null. docdna writes a pointer row, not a file. |
| `detect_paths` | Where an existing instance might already live. Order is preference order. |
| `system_of_record` | `repo`, or `ask` on every `product` and `org` scoped entry |

**`selects_on` is the terse rule and `baseline_verdict` is what it sets.** Anything more complex than one
predicate lives in `rules.json` and is applied at higher precedence. A document with
`{"always": true}` needs no rule.

**Templates.** v0.1 ships none. From v0.2, a `Y` entry may have `templates/<stage>-<slug>.md` and an `M`
or `R` entry may not. Invariant I1 enforces it.

## 7. `rules.json`

```json
{
  "id": "R-VDP-PUBLISHED",
  "layer": "signal",
  "when": {"all": [
    {"signal": "users.published_package", "is": "present"},
    {"not": {"document": "assure.vdp", "state": "present"}}
  ]},
  "effect": "require",
  "documents": ["assure.vdp"],
  "because": "Published artifact with no private disclosure route.",
  "cite": ["users.published_package"],
  "force": false
}
```

| Field | Values |
| --- | --- |
| `layer` | `baseline` 0, `signal` 10, `overlay` 20, `answer` 30, `override` 40 |
| `effect` | `require` `recommend` `optionalize` `exclude` `ask` `note` |
| `documents` | Catalog ids. Every one must exist. |
| `because` | One sentence, printed verbatim to the user. No placeholders. |
| `cite` | Signal ids or answer keys. Every one must exist. This is what makes an exclusion auditable. |
| `force` | Permits a downgrade. Records the rule id in the manifest when used. |

**Escalation is monotonic.** Order the verdict lattice `not-applicable < optional < recommended <
required`. A rule may raise a document's verdict; it may only lower it when `force: true`. Without this,
a badly ordered exclusion rule silently deletes a document a regulator expects, and nothing in the output
shows that it happened.

**`effect: exclude` requires `because`, `cite`, and `revisit_when`.** An exclusion without a tripwire is a
guess wearing a decision's clothes.

```json
{"effect": "exclude",
 "revisit_when": {"any": [{"signal": "data.pii", "gte": 1},
                          {"signal": "sec.authn", "is": "present"}]}}
```

## 8. `archetypes.json` and `interview.json`

**Primaries** carry `weights`, an object of predicate-to-points, and `baseline`, the document count the
report prints. Score is matched weight over total positive weight. Primary is the argmax.

```json
{"id": "oss-library", "baseline": 9,
 "weights": [{"when": {"signal": "users.published_package", "is": "present"}, "points": 30}],
 "requires_absent": ["iface.http"]}
```

- `floor`: below this top score the archetype is `unknown` and the interview is mandatory.
- `counterfactual_margin`: 15. Within this, emit `archetype_counterfactual` with the document delta and
  refuse to write any `assure` stage document.

**Overlays** are additive and carry `when` plus `adds`, a list of document ids. Overlays never remove.

**Questions** carry `id`, `prompt`, `answers`, `default_from` (a list of predicate-to-value rules, first
match wins), `fallback`, and `counterfactual`, the sentence printed in the dial.

```json
{"id": "q3_authorizer", "fallback": "none",
 "default_from": [{"when": {"all": [{"signal": "jur.gc", "is": "hint"},
                                    {"signal": "users.gc_design_system", "is": "present"}]},
                   "value": "government-authorizer"}],
 "counterfactual": "a government buyer is in the loop"}
```

**`q4_decides_about_people` has an empty `default_from` and a `fallback` of `no`.** No signal may set it.
Invariant I5.

## 9. Invariants

`docdna_select.py` exits nonzero on any of these. They are tested in `tests/test_catalog.py`.

| # | Invariant |
| --- | --- |
| I1 | A template file exists for a `producible` of `M` or `R` |
| I2 | A rule, archetype, overlay, or question references a document id absent from `documents.json` |
| I3 | A predicate or `cite` names a signal id absent from `signals.json` |
| I4 | A rule tests `{"is": "hint"}` and its effect is not `ask` or `note` |
| I5 | Any `default_from` entry exists on `q4_decides_about_people` |
| I6 | A rule sets `require` or `recommend` on a `producible: R` document without an `answer` term in `when` |
| I7 | A rule with `effect: exclude` lacks `because`, `cite`, or `revisit_when` |
| I8 | A document lists a `stage`, `durability`, `scope`, `producible`, or `cadence` outside its enum |
| I9 | Two documents share an id, or two rules share an id |
| I10 | A `product` or `org` scoped document does not set `system_of_record` to `ask` |

I6 is the compliance guardrail in code rather than in prose. No signal alone may make a legal instrument
required. A human answering Q3 or Q5 is the only path, because prose guardrails lose to "just fill it in,
I will review it later".

## 10. Downstream contracts

`docdna_scan.py` output and `.docdna/manifest.json` are specified in the design spec, sections 9.1 and
9.2. Two rules restated here because the catalog depends on them:

- Scanner evidence is capped at `--max-evidence`, default 5, with `evidence_truncated` set. `hits` is
  always the full count.
- `manifest.excluded[]` lives in JSON only. `DOCDNA.md` prints a count plus the exclusions whose
  `revisit_when` is within one signal of firing.
