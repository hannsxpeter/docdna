# Selection

How the engine decides. `catalog/SCHEMA.md` is normative for shapes and enums; this file is the reasoning
behind them. Where the two disagree, SCHEMA.md wins.

The failure mode of a document-selection engine is not "missed a document". It is **asserting that a
document was unnecessary without ever looking**. A missing document is visible and arguable. An
unexamined exclusion is invisible, reads exactly like a considered decision, and is the row an assessor
pulls first. Every rule below exists to make that one outcome structurally hard.

## 1. The design contract

Five rules govern the engine. Each is here for the failure it prevents.

**1. Signals are three-valued, plus a hint.** `present`, `absent`, `unknown`, and `hint`. Absence of
evidence is never encoded as false. *Prevents:* a detector that never ran being read as a detector that
found nothing, which is how a manifest excludes a document with a straight face.

**2. Evidence or it did not happen.** Every `present` signal carries at least one `{path, line, match}`.
A `present` with no evidence record is a scanner bug, and `docdna_scan.py` raises rather than emitting it.
*Prevents:* an unfalsifiable verdict. A signal you cannot open the file behind is an opinion.

**3. Exclusions are decisions, and decisions are auditable.** `not-applicable` requires `because`, `cite`,
and `revisit_when`. Invariant I7 enforces all three. *Prevents:* a laundered gap. "Not applicable" with no
reason is indistinguishable from "we forgot", and only one of those is defensible in a year.

**4. Escalation is monotonic.** A rule may raise a verdict. It may only lower one when it declares
`force: true`, and the rule id is recorded in the manifest when it does. *Prevents:* a badly ordered
exclusion rule silently deleting a document a regulator expects, with nothing in the output showing that
it happened.

**5. Assumed answers are visible with their blast radius.** An unattended run still produces a manifest.
Every inferred answer is labelled `assumed`, carries the signal that produced it, and prints a
counterfactual stating what changes if it is wrong. *Prevents:* the questionnaire. A tool that demands
seven answers before saying anything useful gets closed on the third question.

## 2. The signal model

Four states, and the fourth is a correction the adversarial pass forced.

| State | What the scanner is saying | What a rule may do with it |
| --- | --- | --- |
| `present` | I looked, I found it, here is the evidence | set a verdict |
| `absent` | I looked and there is nothing | set a verdict |
| `unknown` | I did not look, or I refuse to guess | open a question. Never silence a document. |
| `hint` | Something matched and it is not enough | open a question. **Never set a verdict.** |

**`unknown` is not `absent`, and conflating them is the whole ballgame.** Pass-2 greps are gated on pass-1
signals: the AI family on a manifest dependency, the interface family on service or deploy candidates, the
data family on migrations, an ORM, or DDL. A gate that does not fire means the grep never ran. Reporting
that as `absent` converts "we did not look" into "we decided this does not apply", and those two sentences
have opposite consequences in front of an auditor.

**`hint` is a distinct state rather than a low-confidence `present` for exactly one reason: so that no rule
can consume it as `present` by accident.** All eleven `jur.*` signals are capped at `hint` by `max_state`,
because every jurisdiction proxy tested misfired on real code. A region-name constant fired both EU and
GC. A GDPR library's README fired EU on prose. An `en` plus `fr` locale pair fired GC on a project with no
Canadian nexus at all. The first two ship as `tests/fixtures/region_const` and `tests/fixtures/gdpr_lib`,
precisely so the demotion cannot be quietly undone. The third is why `jur.gc` now requires `fr-CA` rather
than `fr`, plus a second independent signal.

`{"signal": "x", "gte": 1}` implies `present`, so it is the idiomatic "at least one real hit" test and can
never be satisfied by a hint. Invariant I4 rejects any rule that tests `{"is": "hint"}` and sets a verdict.

**Nine signals refuse to guess.** They carry no detector, they are always `unknown`, and each names the
question that resolves it.

| Signal | Question | Why no proxy is good enough |
| --- | --- | --- |
| `users.repo_visibility` | Q1 | A private mirror and a public repo look identical on disk |
| `users.external_count` | Q1 | Nothing in a repo counts its users |
| `ops.operator_identity` | Q2 | CD config proves deployment, never who carries the pager |
| `jur.authorizer` | Q3 | A compliance folder proves someone cared, not that a body can block a release |
| `ops.rto` / `ops.rpo` / `ops.sla_exists` | Q6 | These are numbers, and no number is ever generated |
| `docs.system_of_record` | Q8 | A repo cannot see Confluence |
| `data.lawful_basis` | Q5 | A legal conclusion, not a property of the code |

Every available proxy for these is wrong often enough to produce a confidently false compliance verdict,
which is the failure most worth avoiding and the reason the list is a design output rather than a backlog.

## 3. Archetypes

Eight primaries, mutually exclusive, plus an `unknown` floor: `solo-utility`, `oss-library`,
`internal-service`, `commercial-saas`, `client-application`, `data-platform`, `embedded-device`,
`research-artifact`. Each carries a `baseline`, the document count the report prints, from 4 for a solo
utility to 31 for a commercial SaaS.

**Scoring is a weighted evidence sum, not a decision tree.** Score is matched points over total positive
points; the primary is the argmax. A tree gives you one answer, no runner-up, and nothing to show when it
is wrong. A sum gives you a second place and a distance, which is what the counterfactual needs.

- **`floor` is 0.45.** Below it the archetype is `unknown` and the interview stops being optional.
- **`counterfactual_margin` is 15 points.** Within that gap, the manifest carries the document delta to the
  runner-up, and no `assure`-stage document is written until a human confirms the archetype. Under low
  confidence the selected rows carry `write_block` and say so.
- **`requires_absent` is a veto, not a penalty.** It zeroes the score. `oss-library` is vetoed by
  `iface.http`, `internal-service` by `users.public_signup`, `research-artifact` by any deploy signal. A
  published package that also serves HTTP is not a library, and no amount of matched weight should make it
  one.
- **Confidence** is `high` only at a 15-point gap *and* a score of at least 0.70. One of the two gives
  `medium`. Neither gives `low`.

**Five overlays, additive, and they never remove:** `ai-system`, `shipped-artifact`, `public-ui`,
`operated-by-others`, `agent-skill-package`. An overlay answers "what extra obligations", not "what is this
thing". Modelling payments or safety-critical or AI as primaries forces a false choice at the top of the
tree, duplicates every baseline row under each branch, and guarantees that the one system which is both
gets the wrong set. Scale is rejected as a primary for the same reason: it is a continuum and it arrives as
signals.

## 4. The interview

**Eight questions. Zero are asked on the first run.**

The machinery that makes that possible is signal-derived defaults, `source: assumed`, and per-answer
counterfactuals. Assume, show the assumption with its blast radius, and let the user correct in one
sentence.

| # | Question | Assumed from | Fallback |
| --- | --- | --- | --- |
| `q1_users` | Who uses this, besides you? | published package, public signup, CD | `nobody` |
| `q2_operator` | Who runs it, and can they page someone? | any `deploy.cd` | `not-deployed` |
| `q3_authorizer` | Is there an external body that can block a release? | corroborated jurisdiction hint, compliance program | `none` |
| `q4_decides_about_people` | Does it decide about individual people? | **nothing. No signal may set it.** | `no` |
| `q5_markets` | Which markets do your users sit in? | corroborated jurisdiction hint | `my-org-only` |
| `q6_downtime` | If it were down for a day, what breaks? | on-call config, CD without on-call | `nothing` |
| `q7_maintenance` | Will anyone maintain these documents? | CODEOWNERS, single author | `snapshot` |
| `q8_doc_location` | Where does your documentation live? | a docs directory, a site generator, or a README | `repo` |

Three of the eight carry a rule that is not a tuning choice:

**Q4 defaults to `no` unconditionally, and invariant I5 enforces it in code.** Whether a system makes
automated decisions about individuals is not detectable from token frequency. The signal that used to try
fired five times on a parser containing `candidates = [n for n in nodes if n.eligible]`. Eight documents
hang off this answer in the shipped catalog, among them the compliance register, the data classification,
and the threat model, so a lexicon hit may open the question and may never answer it.

**Q7 is not cosmetic.** Under `snapshot`, output is capped to the mechanically regenerable set and the
judgment-bearing set is refused with a stated reason. A document regenerable in one command is safe to
leave unmaintained. A threat model is not.

**Q8 is stated in every first report whether or not it is asked.** "I only see documentation committed to
this repo" is the difference between a tool that has met a real company and one that has not. One false
"absent" for a document that lives in Confluence destroys trust in every other row on the page.

**Answers persist.** They land in `.docdna/manifest.json` under `interview` with `source: user`, and they
are read back on the next run, so re-running is non-interactive and idempotent. Correcting one is one flag:

```sh
python3 docdna_select.py --answer q2_operator=separate-ops-team <repo>
```

## 5. The counterfactual dial

Every report ends with the same block, computed by re-running the rule engine once per row with one answer
flipped:

```
Currently required: 19 documents.

  a separate ops team runs this        +11
  you sell to EU customers              +9
  a government buyer is in the loop    +19
```

It costs one extra engine pass per row and it converts a formless anxiety into a model the user can
manipulate. It is also the artifact a lead forwards upward, because it prices a business decision in units
of work. **The dial is why the interview can be skipped:** a wrong assumption is cheap when its cost is
printed next to it.

## 6. Verdict times state equals action

Four verdicts describe need. State describes what exists. The action is the product, and it is a lookup,
not a judgment.

| | absent | present-fresh | present-drifted | present-stub | present-elsewhere |
| --- | --- | --- | --- | --- | --- |
| **required** | `write` | `adopt` | `refresh` | `complete` | `confirm` |
| **recommended** | `offer` | `adopt` | `refresh` | `complete` | `confirm` |
| **optional** | `note` | `adopt` | `note` | `note` | `note` |
| **not-applicable** | `skip` | `orphan` | `orphan` | `orphan` | `skip` |

- **`adopt` is the cheap win.** The document is fine and only lacks lifecycle metadata. Most first runs
  have more of these than anything else.
- **`orphan` is a real result**, not an error: a document the repo carries that nothing in the profile
  justifies. That is where doc rot starts, and nothing else reports it.
- **`confirm` exists because of Q8.** A `product` or `org` scoped row whose system of record is external is
  not absent; it is somewhere this tool cannot see, and the honest action is to ask.

## 7. Precedence and monotonic escalation

Rules are sorted by layer, then by id, and applied in that order.

| Layer | Precedence | Shipped rules |
| --- | --- | --- |
| Archetype baseline | 0 | 14 |
| Signal deltas | 10 | 33 |
| Overlays | 20 | 10 |
| Interview answers | 30 | 29 |
| User overrides read back from the manifest | 40 | 2 |

Order the verdict lattice `not-applicable < optional < recommended < required`. **Within and across layers,
a rule may only raise a document's verdict.** A rule that would lower one is refused and the refusal is
recorded on the row as `downgrade_refused`, unless the rule declares `force: true`, in which case the
forcing rule id is recorded as `forced_by`. Either way the manifest shows what happened.

The property matters because precedence alone does not save you. A later layer is not a more correct
layer; it is only a later one. Without monotonicity, an answer-layer exclusion written to trim noise for a
small project quietly removes a document that a signal-layer rule required on evidence, and the output
looks the same as if the document had never been selected.

Two constraints ride on top of the lattice:

**No signal alone may make a legal instrument required.** Invariant I6 rejects any rule that sets `require`
or `recommend` on a `producible: R` document without an `answer` term in its `when`. A human answering Q3
or Q5 is the only path. This is enforced in code and not in prose because prose guardrails lose to "just
fill it in, I will review it later".

**Every exclusion carries its tripwire into the manifest.** `excluded[]` records the rule, the `because`,
the `cite` list, and the `revisit_when` predicate that would make the document required again. Check
re-evaluates every one of them and leads with the ones now firing. That is the only reason to run this tool
a second time, and it is why an exclusion is written as a decision with an expiry rather than as a silence.
