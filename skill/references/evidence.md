# Evidence discipline

Normative. This governs every sentence docdna writes.

The failure mode is not missing documentation. It is documentation that reads authoritative and is wrong,
because a template had a slot and the model filled it. Everything below exists to make that specific
outcome structurally hard rather than discouraged.

## 1. The rule

**Every claim block carries a citation or a GAP marker. There is no third state.**

A claim block is a paragraph, a bullet, or a table row. That unit is greppable, which is what makes the
rule enforceable instead of aspirational. `docdna_check.py` counts claim blocks and citations per document
and reports the ratio.

## 2. What the checker can and cannot establish

The rule above binds the writer and does not bend. The checker that enforces it is a net, and the mesh has
a known size. Both statements are true at once, and stating only the first is the confident fiction this
skill exists to prevent. An overclaimed check costs more than a missing one, because a reader who finds
the gap discounts every other claim in the document.

**It can establish:**

- A `code` citation resolves. The file exists in the working tree and the named symbol or verbatim anchor
  occurs somewhere in it.
- A number in the claim block occurs **within four lines of the symbol or anchor the citation names**. A
  citation names a place, so it backs the numbers written at that place and no others. A citation that
  names a file and no place inside it resolves and binds nothing, because a constants module holding
  `MAX_RETRIES` and `PAGE_SIZE` is not a source for every figure in the tree. This is proximity binding,
  and Check and `--verify` open the same four-line window.
- A `ref` citation resolves to a reference file **inside the repository under analysis** and its anchor
  hits. A missing verified date is flagged; whether the date is honest is not checkable.
- Structural facts. Every claim block carries a citation or a GAP, and no citation is a bare line number.

**It cannot establish, in four places:**

- **A `run:` citation is never executed.** docdna is read-only and non-goal 7 forbids running anything, so
  nothing runs the command and nothing captures the output. The writer supplies both, and the verifier
  accepts that transcript as the evidence for it. A `run:` citation is therefore **self-attested**, and a
  number resting only on a `run:` citation is **unverified**. It supports no number in either tool: both
  report it as SELF-ATTESTED, NOT VERIFIED, `--verify` never opens its verdict with the word clean while
  one is present, and a claim block whose only citations are `run:` citations is counted apart from the
  cited blocks. What remains structural is that nothing runs the command. Closing that would mean
  executing repository commands, which is a different and more dangerous tool.
- **A `human:` attestation is validated by shape only.** A handle beginning with `@` and a parseable ISO
  date. That a person actually said it, that the person exists, and that the number is right are all
  outside what the tool can see. A `human:` citation is the one way a number enters uncited, so it
  exempts its claim block from the number rule and is the widest opening in the net. It is never silent:
  both tools record the block as resting on an attestation rather than on the repository.
- **Intent is unreadable.** A number sitting near a citation is not proof the citation supports the claim.
  `resolve_code` checks that an anchor exists, never that it means what the sentence says. That is why
  section 4 forces exhaustive and negative claims onto a `run` citation at write time: no later pass
  recovers it.
- **A cited file can itself be wrong.** A citation proves the repository says it. It never proves it is
  true.

So the guarantee, stated so it survives contact with a skeptic: **docdna never generates a number. That is
mechanically enforced wherever the number rests on `code` or `ref` evidence, and self-attested wherever it
rests on `run` or `human`.** Read a `run` number as a claim the writer wrote out in full so you can re-run
it yourself. That is the only reason the command is spelled out rather than summarized.

## 3. Four evidence classes, and no fifth

| Class | Syntax | Means |
| --- | --- | --- |
| `code` | ``[`src/api/routes.py#register_routes`]`` or ``[`src/api/routes.py` "def register_routes"]`` | A path plus a symbol or a verbatim anchor, at the recorded commit |
| `run` | ``[run: `python3 -m pytest --collect-only -q` -> 214 tests]`` | A named command and its captured output |
| `ref` | `[ref: docs/regime-facts/eu.md#annex-iv, verified 2026-07-31]` | A reference file **in this repository**, carrying its own verification date |
| `human` | `[human: @hpp 2026-07-31]` | Supplied by a person in this session, attributed |

**Never a bare line number.** Adding one import above a citation invalidates every line anchor in the
file, so a document verified clean at commit A reports mass failure at commit A plus one. A symbol name or
a verbatim anchor string survives reformatting, reordering, and insertion, and it can be relocated with a
grep. This is the difference between a citation that decays gracefully and one that decays catastrophically.

**A `ref` resolves inside the repository under analysis, and nowhere else.** docdna's own shipped files
are not evidence about somebody's project: no author of that repository controls a word of them, so a
`ref` that lands in the skill laundered the same number into every install. `--verify` refuses one as a
blocker rather than downgrading it to a note. If the reference belongs to the project, commit it to the
project.

**There is deliberately no class for model knowledge.** "The EU AI Act Annex IV has nine areas" is a `ref`,
and the reference file, committed to this repository, carries the date somebody checked it. If a claim
cannot be traced to one of the four classes, it is not a claim, it is a recollection, and it does not go
in a document.

## 4. Exhaustive and negative claims need a `run` citation

A `code` citation resolves one symbol in one file. It can show that a thing exists. It can never show that
a thing exists nowhere, and it can never show that a property holds for every member of a set.

**Any claim of the shape "every X has Y", "no X does Y", "there are no X", or "X appears nowhere in this
repository" is carried by a `run` citation or it is not written.** The citation carries the search command
and its captured output, exactly as a count does:

``[run: `grep -rln "FEATURE_CHECKOUT" src/` -> no matches]``

Three outs, in preference order:

1. **Run the search and cite it.** The command and its output are the evidence, and a reader can re-run it.
2. **Narrow the claim to the set actually inspected, and name that set.** "Each of the eleven keys declared
   in `.env.example` has a read site" is a different, weaker, honest claim than "every declared key has a
   read site", and eleven `code` citations prove it. Naming the set is what makes the narrowing real; "the
   settings I checked" is not a set.
3. **Emit an `unverifiable` GAP.** The search is not runnable here, so the question goes to a person
   instead of into the document as a sentence.

This rule is stated at write time because the verification pass cannot recover it later. `resolve_code`
checks that the anchor exists, not that it supports the claim, so a negative universal carrying a `code`
citation passes verification and is still fiction. It is the one failure class the pipeline cannot catch
downstream of the sentence being written.

## 5. The verification pass

After writing and before reporting, Backfill re-reads every citation it just wrote and labels it. The
stance is adversarial: assume every claim is wrong until the file proves it right.

| Label | Action |
| --- | --- |
| PASS | The cited symbol or anchor supports the claim as written |
| FAIL | It does not. **Delete the claim.** Do not soften it; a hedge still reads as documentation. |
| UNVERIFIABLE | The anchor resolves but does not settle the claim. Convert to an `unverifiable` GAP. |

**FAIL auto-deletes only in Backfill, and only against text docdna wrote in this run.** In Check mode,
against documentation a person wrote, FAIL flags and a human decides. A tool that deletes somebody's prose
on a resolution heuristic gets uninstalled once, and correctly.

## 6. The four anti-theater rules

Named so they can be invoked in review by name.

**Paper theater.** A sentence true of any project. Test by substitution: swap the project name for a
competitor's and the stack for a different one. "The system follows a layered architecture with separation
of concerns" survives substitution and is therefore worthless. "Requests enter through `cmd/api/main.go`,
which mounts four route groups and no middleware other than request logging" does not survive
substitution and is therefore documentation.

**Checkbox headings.** A section whose body is entirely GAP markers and boilerplate is a request for
information wearing a heading. If a document's cited claim blocks are fewer than its GAP markers, the
document is not written; it is listed as `status: not-started` with its blockers attached.

**Regime cosplay.** A privacy impact assessment for a project with no personal data. An operational
readiness review for a library with no runtime service. Every document in the manifest names the signal
that selected it, with a file path. A document that cannot name its triggering signal is not required.

**Confident fiction.** The killer, and the one specific to this skill. **No number is ever generated.**
Not a recovery time objective, a recovery point objective, an SLA, an availability target, a capacity
figure, a retention period, a support-window end date, an error budget, or a review cadence. Every one of
these appears in real templates as a slot and every one is a decision a human owns. Numbers are cited or
they are `human-input` GAPs.

**The rule is absolute for the writer.** It does not weaken, and no citation class is a license to invent
a figure and dress it. Enforcement is narrower than the rule, deliberately and permanently: section 2
names the four places the checker cannot reach, and a `run:` number is self-attested there. Write as
though nothing checks you, because for `run` and `human` numbers nothing does.

A fifth rule covers the manifest rather than the documents: **`not-applicable` requires a reason and a
signal.** An unexplained exclusion is worse than a missing document, because it launders a gap into a
decision.

## 7. Sensitivity

Every catalog entry carries `sensitivity`. A threat model, an access control inventory, and a disaster
recovery plan are sensitive artifacts in their own right.

**docdna refuses to write an `internal` or higher document into a repository whose visibility is public or
unknown without explicit confirmation.** Repository visibility is one of the nine things the scanner
refuses to guess, so on a first run this is a question, not an inference.

The confirmation is `docdna_backfill.py --confirm-sensitive`. It is not a way past the refusal; it is a
person recording that they know this repository may be public and that this document may be read by
anyone, and accepting that. If the answer is instead that the repository is private, the honest fix is to
record the fact once with `docdna_select.py --answer q1_users=<value>`, which settles it for every later
run rather than for this one invocation.

## 8. Reconstructed decision records

ADRs are immutable, so a fabricated rationale is permanently in the record and can only be superseded,
never corrected. That is the one document class where mistakes cannot be edited away, and it is the one
being reconstructed from inference. Four rules, all normative:

- Reconstructed decisions are minted in a distinct id space, `adr-draft-20260731-01`, date-prefixed to
  survive concurrent branches, and never renumbered into the accepted sequence without an explicit human
  accept step.
- Frontmatter carries `retro: true` and `derivation: derived`. Status is `accepted`, not `proposed`. The
  decision was made, shipped, and is running; `proposed` on a live decision either invites re-litigation
  or gets mistaken for a contemporaneous record.
- The Considered Options section is **absent**, not filled with "unknown". A GAP marker sits in its place.
- A `retro: true` record with a populated Considered Options section and no `human:` citation is a
  confident-fiction lint error.
