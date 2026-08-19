# Compliance, and every refusal

<!-- Implements: P-MUST-05 -->

The short version: docdna will help you assemble the evidence an assessor asks for, and it will not write
the document you sign. That line is enforced in code, not promised in prose.

## Why it does not generate a SOC 2 document

The catalog carries the SOC 2, HIPAA, PCI, GDPR, EU AI Act, CRA, and ITSG-33 rows. It does not follow that
your repository owes any of them.

**Ninety-six entries means ninety-six rows ruled on**, most of them not applicable with a stated reason and
a tripwire. It does not mean ninety-six documents written.

## Three worked examples

Three fixtures ship in this repository, each surveyed with no questions asked:

| Fixture | Selected | Excluded | HIPAA | PCI | SOC 2 |
| --- | --- | --- | --- | --- | --- |
| `internal_service`, a Django app | 41 | 55 | not applicable | not applicable | not applicable |
| `health_service`, FHIR and patient records | 35 | 61 | **optional**, PHI inventory recommended | not applicable | not applicable |
| `payments_service`, Stripe | 33 | 63 | not applicable | **optional**, data flow recommended | not applicable |

A plain service is told it owes nothing under any of the three, and is not asked about them either.

SOC 2 stays quiet on all three because none carries a compliance program, which is correct: SOC 2 is
something an organisation elects to undergo, not something a codebase implies.

## The asymmetry inside HIPAA

Note what happens once health data is detected. `assure.phi-inventory` becomes **recommended**, because an
inventory of where health data sits is derivable from a schema.

The risk assessment and the business associate agreement are **optional and never required**, because a
signal must not make a legal instrument mandatory. Only your answer to "is there an external body that can
audit or authorize this" can do that. That is invariant I6, and it is enforced at catalog load time rather
than left to the good behaviour of whoever edits the catalog next.

## The seventeen refusals

Seventeen of the ninety-six catalog entries are `producible: R`, and R is a refusal the code enforces rather
than a promise the prose makes. `docdna_backfill.py` declines every one of them and prints why, plus the
role that must sign it.

The refused set covers the System Security Plan and authority to operate, the HIPAA security risk assessment
and business associate agreement, the SOC 2 system description, the PCI self-assessment, the impact
assessment family (PIA, DPIA, AIA, FRIA), the CRA technical file and EU declaration of conformity, AI Act
Annex IV and GPAI documentation, the accessibility conformance report and statement, and the secure design
review, penetration test, and training records.

Ask for one and it declines by name:

> **producible R: docdna never writes this document.** A security risk assessment is a regulated
> deliverable under the HIPAA Security Rule and is evidence a covered entity or business associate stands
> behind. docdna writes the inventory that feeds it and refuses the assessment itself.
> **Signed by the covered entity's Security Official.**

Naming the signer is what makes a refusal actionable rather than merely obstructive.

Two invariants hold this in place. **I6**: an R entry may never be raised to `required` by a signal, only by
an interview answer, because a grep that finds an IAM role must not make a System Security Plan required.
**I1**: the build fails if a template ever ships for an R entry.

## What it writes instead

The inputs, under `docs/assure/inputs/`: the attack surface, the control evidence index with its unknown
rows, the PHI inventory, the automated accessibility results. The signature line stays empty.

A further thirty-seven entries are `producible: M`, manifest only. docdna tracks the row, names the signal
that selected it, and states what a human has to supply. That is where the threat model, the runbook, the
access control inventory, and the data classification register live.

## Where the regulatory facts come from

Regulatory facts live in [../skill/references/regime-facts/](../skill/references/regime-facts/), six files
carrying `verified:` dates.

Forty-seven facts are cited to primary sources: eCFR, the AICPA, the PCI SSC, EUR-Lex, NIST, and the
Canadian Centre for Cyber Security. Three could not be confirmed and sit in an explicit "Unverified, do not
rely on" section rather than in the body. Vendor summaries and law-firm explainers were rejected as
non-primary.

CI reports the age of every file and fails past a year. Ownership and cadence are in
[CATALOG-MAINTENANCE.md](CATALOG-MAINTENANCE.md). An unmaintained dated file is worse than none, because it
asserts current legal fact with confidence while being stale.

## The rest of the refusals

Compliance is one part of a wider stance. The full set:

### No number is ever generated

Not a recovery time objective, recovery point objective, SLA, availability target, capacity figure,
retention period, or error budget. Every one is a decision a person owns. Numbers are cited or they are
gaps.

The rule is absolute for the writer. Enforcement is narrower, and the difference is stated rather than
papered over:

- A number resting on a `code` or `ref` citation **is checked mechanically**, against the four lines around
  the symbol or anchor the citation names, in a file inside the repository under analysis. A citation that
  names a file and no place inside it resolves and binds nothing.
- A number resting on a `run:` citation is **self-attested and supports nothing**. docdna never runs the
  documented repository's own commands, its tests, its scanners, its application, or anything on the
  network, so neither the command nor its output was ever observed. Both tools report the citation as
  SELF-ATTESTED, NOT VERIFIED, and `--verify` never calls such a document clean.
- A `human:` attestation is **checked for shape only** and is recorded as an attestation rather than a
  verification.

Those limits are structural, not a backlog item, and
[../skill/references/evidence.md](../skill/references/evidence.md) names all four classes in its second
section.

### Product proof states

Version 1.4.0 exposes the product-claim registry with
`python3 skill/scripts/docdna_proof.py --json`. The terms remain deliberately separate:

- **Verified** means a deterministic repository-local check observed the registered evidence.
- **Attested** means a person supplied a shape-checked `human:` statement that DocDNA did not independently
  establish.
- **Self-attested** means a `run:` command and output were recorded together, but DocDNA did not execute
  the target repository's command.
- **Refused** means the requested evidence class, unsafe input, or proof promotion is outside the
  verifier's authority.

The registry's shipped, unit-tested, install-tested, artifact-proven, replay-tested, measured,
adjudicated, host-capture-ready, host-captured, and external-tool-dependent levels do not collapse into
"verified." Source-checkout mode can inspect registered evidence paths and golden replay IDs. Installed
mode is read-only and validates promotion structure only, because checkout-only evidence and replay
fixtures are not shipped. Neither result proves host parity, certification, legal sufficiency, or a host
run. Exit code 0 means the requested validation completed, 1 means a replayed outcome failed, and 2 means
invalid or unsafe control data prevented validation. Recovery is to inspect the named registry error or
reinstall trusted release bytes.

### No legal instrument

Covered above. Seventeen entries, refused in code, each naming its signer.

### No runbook procedure

An alert-to-runbook coverage table is derivable and safe. A remediation executed at 03:00 by somebody who
did not write the system is the highest-consequence hallucination in the catalog, so docdna writes the index
and leaves the procedure to a human.

### No software bill of materials

Real dependency resolution is not a standard-library job. docdna detects the ecosystem, emits the exact
`syft` or `cdxgen` command, and records that command's output as evidence. A hand-written dependency list is
a lie with a filename.

### No code changes

It reports where code and document disagree. It will not reconcile them by editing the code.

### No legal advice

It reports the signal, names the regime that signal might trigger, and says to confirm with counsel. It does
not assert that a regime applies to you.

### No certification, attestation, or signature

No authority to operate, CE marking, declaration of conformity, or completed VPAT. It produces the inputs an
assessor needs and names who must sign, empty.

## Related

- [HOW-IT-DECIDES.md](HOW-IT-DECIDES.md), how a row gets ruled in or out in the first place
- [MEASUREMENT.md](MEASUREMENT.md), what has been measured about this tool and what has not
- [../skill/references/evidence.md](../skill/references/evidence.md), the citation and gap rules
- [../skill/catalog/SCHEMA.md](../skill/catalog/SCHEMA.md), the ten invariants in normative form
