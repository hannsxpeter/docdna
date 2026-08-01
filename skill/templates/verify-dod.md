# Definition of Ready and Definition of Done template

Catalog id `verify.dod`. Default path `docs/verify/definition-of-done.md`. Producible Y. GAP prefix `DOD`.

Normative. This file is an instruction set, not prose to copy. **No sentence below may appear in the
document.**

Most Definition of Done documents are a wish list written once and never enforced. This one is derived the
other way round: from what the pipeline actually refuses to merge. **The document's central artifact is a
two-column table, ENFORCED against CLAIMED, and the distance between the columns is the finding.** A row
that is claimed and not enforced is a promise nobody keeps. A row that is enforced and not claimed is a
rule people learn by having a pull request blocked.

## Skeleton, in this order

1. The frontmatter block from the write plan's `frontmatter` object. See `_frontmatter.md`.
2. The reconstruction banner, verbatim from the write plan's `banner`. See `_banner.md`.
3. A single `#` heading.
4. The sections below, in order. The enforced-against-claimed table comes first, before any prose,
   because it is the reason to open the document.
5. The document control block. See `_document-control.md`.

## Rules that outrank every section below

- Every table row carries a citation in each populated column. ENFORCED cites the mechanism, CLAIMED cites
  the sentence that claims it.
- **ENFORCED means a merge is blocked without it.** A workflow that runs and does not gate is not
  enforcement; it is a signal. Put it in the ENFORCED column only when a required check, a branch
  protection rule, a merge queue configuration, or a required reviewer rule makes it blocking, and cite
  that mechanism.
- **Branch protection lives on the forge, not in the repository.** Unless a committed settings file
  declares it, docdna cannot see whether a check is required. Never write "required" from the existence of
  a workflow. That cell is an `unverifiable` GAP carrying the exact command a human can run to settle it.
- **No number is generated.** Not a coverage threshold, a required approval count, a review turnaround
  time, a maximum pull request size, or a stale branch window. Each is copied from a committed
  configuration and cited, or it is a `human-input` GAP.
- A checklist item in a pull request template is a claim, never enforcement. An unchecked box has never
  blocked a merge.
- **An exhaustive or negative claim is a claim about a search, not about a symbol.** "Every claimed item
  maps to a mechanism" and "nothing else gates a merge" are carried by a `run` citation holding the
  command and its output, or they are narrowed to the named set actually inspected, or they are an
  `unverifiable` GAP. A `code` citation resolves one symbol in one file and cannot support either shape.
  See `references/evidence.md`.

## `## What is enforced, and what is merely claimed`

**Evidence.** From the write plan: `evidence.workflows` for job names and triggers,
`evidence.enforcement_anchors` for committed branch protection and merge queue keys, and
`evidence.claimed_checklist` for pull request template and contributing guide items. Plus CODEOWNERS for
required reviewers.

**Write.** One table, three columns: requirement, ENFORCED by, CLAIMED in. One row per distinct
requirement, merged across sources so a requirement appearing in both columns is one row and not two.
Populate a cell only with a citation. Order rows: enforced and claimed first, then enforced only, then
claimed only. That ordering puts the finding at the bottom where a reader lands last.

**Absent per cell.** Nothing enforces a claimed item:
`kind=not-implemented sev=major asks="<claim> is in the pull request template and nothing in the pipeline
checks it. Should it be enforced or dropped?"`

**Numbers.** A coverage threshold appears only if a committed configuration sets it, cited to that
configuration and not to the badge in the README.

## `## Enforced automatically`

**Evidence.** `evidence.workflows`: the jobs, the triggers, and the steps inside each job. Only workflows
whose trigger includes the pull request event can gate a pull request; a workflow that runs on push to the
default branch runs after the merge and gates nothing.

**Write.** One row per job: job name, what it runs, which trigger fires it. Cite each to the workflow file
and the job key as a verbatim anchor. Then one sentence on whether being required is visible from the
repository, naming the committed files checked for it. "Nothing in this repository declares required
checks" is a claim about a search, so it carries the search, for example
``[run: `ls .github/settings.yml .github/rulesets 2>&1` -> No such file or directory]``, or it is written
as the GAP below instead.

**Absent.** No committed file declares required checks:
`kind=unverifiable sev=blocker asks="Which of these checks are required to merge? Branch protection is a
forge setting and this repository does not commit it."` Give the human the command that settles it, and
label the eventual answer a `run` citation:
``[run: `gh api repos/OWNER/REPO/branches/BRANCH/protection` -> ...]``.

## `## Enforced by a person`

**Evidence.** CODEOWNERS patterns and owners, a committed `required_approving_review_count`, a merge queue
configuration, and any committed rule requiring conversation resolution.

**Write.** One row per rule: what triggers the human gate, who it routes to, and the citation. Present
CODEOWNERS as routing plus, where a committed setting says so, as a blocking requirement.

**Absent.** No CODEOWNERS and no committed review requirement:
`kind=human-input sev=major asks="How many approvals does a change need, and from whom?"`

## `## Claimed and not enforced`

**Evidence.** `evidence.claimed_checklist` items with no matching mechanism in the enforced sections.

**Write.** One bullet per item, quoting the checklist line verbatim and citing the file it lives in. Do
not soften the framing and do not propose the automation. Naming the gap is this document's job;
closing it is a decision with a cost.

**Absent.** "Every claimed item maps to a mechanism" is safe to write here in exactly one form, because
the claimed set is closed and committed: name the file and the count, as in "each of the seven checklist
items in `.github/PULL_REQUEST_TEMPLATE.md` maps to a mechanism in the table above", and let the per-item
citations in that table carry it. Never write the unbounded version, which asserts that no claim exists
anywhere in the repository without a mechanism. If contributing guides or other documents also carry
claims and you did not read them, say which files the sentence covers, or emit
`kind=unverifiable sev=minor asks="Are there merge requirements claimed outside the pull request template?
Only the committed template was read."` A genuine full mapping is a rare and good finding, which is why it
has to be the real claim and not the flattering one.

## `## Enforced and not written down`

**Evidence.** Jobs and rules from the enforced sections with no matching checklist item or contributing
guide sentence.

**Write.** One bullet per mechanism, cited. These are the rules a new contributor discovers by being
blocked, and surfacing them is the cheapest onboarding improvement in the repository.

## `## Definition of Ready`

**Evidence.** Committed issue templates, their required fields, and any label-gating automation.

**Write.** One row per required field in an issue template, cited to the template. That is the whole
derivable surface of readiness.

**Absent.** No issue templates:
`kind=human-input sev=major asks="What has to be true before work starts? Nothing in the repository
records an entry condition."` Do not compose a Definition of Ready. It is an agreement between people and
inventing one puts words in their mouths.

## `## Not visible from this repository`

**Evidence.** The mechanisms that live on the forge or in a separate system: branch protection, rulesets,
merge queue enablement, required environments, deployment approvals, and any external status check.

**Write.** One bullet per invisible mechanism with the command or screen that would settle it. This
section is what stops a reader treating the ENFORCED column as complete.

## Refuse to write

- If the repository has no CI configuration, no pull request template, and no CODEOWNERS, there is no
  enforcement and no claim to compare. Report that and write no file.
- If cited claim blocks come out fewer than GAP markers, record `status: not-started` with the blockers
  and create no file.
