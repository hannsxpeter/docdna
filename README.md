# docdna

[![CI](https://github.com/hannsxpeter/docdna/actions/workflows/ci.yml/badge.svg)](https://github.com/hannsxpeter/docdna/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](#get-started-in-two-minutes)
[![Agent skill](https://img.shields.io/badge/agent%20skill-SKILL.md-8A2BE2)](skill/SKILL.md)

### Which documents does this project actually owe?

**docdna reads your code and answers that question, with receipts.**

Point it at a codebase. It comes back with three things:

1. **The documents this project genuinely needs**, and what in the code says so.
2. **The documents it does not need**, why not, and a reminder that fires the day that answer stops being
   true.
3. **The documents it can write for you right now**, drawn from the code, with a source citation on
   every claim.

Nothing is asserted that the repository cannot prove. Every sentence docdna writes either cites a place in
your code or is openly marked as a gap for a human to fill. There is no third option, and that constraint
is the whole product.

No account, no server, no upload, no build step. It is a single folder of standard-library Python that your
coding assistant runs on your machine.

## Who this is for

| If you are | docdna gives you |
| --- | --- |
| **Leading a team** | A defensible answer to "what documentation do we owe, and what are we missing?" instead of a vague sense of dread |
| **Handing a project over** | The set of documents that actually survives the handover, written from the code rather than from memory |
| **Preparing for an audit or review** | A ledger of every document ruled in or out, each with a reason and a citation an assessor can check |
| **Writing the docs yourself** | A first draft of the mechanical documents, so your time goes to the parts only a human can write |
| **An engineer who just wants the docs done** | Ten documents generated from the code, cited, in one command |

You do not need to be the person who wrote the code. You do not need to know which documents exist in the
world. That is the part docdna is for.

## The problem, in plain terms

The documents that would save you during a handover, an audit, or somebody's last day were never written,
because nobody could say which ones this particular project owes.

Generating eighty documents is easy and worthless. The useful and much harder job is deciding that this
repository needs eleven of them, naming which eleven and why, saying out loud which forty-nine were ruled
out and on what grounds, and arranging for those rulings to speak up when they stop being true.

Existing tools do not do this. Linters, documentation generators, and link checkers all work on what
already exists: they will tell you a document is malformed, or that a link inside it is broken. None of
them decides what should exist, and none of them will defend an absence. That gap is what docdna fills.

## Get started in two minutes

```sh
git clone --branch v1.2.1 --depth 1 https://github.com/hannsxpeter/docdna.git
cd docdna
./install.sh claude      # or: all | codex | cursor | windsurf
```

Restart your assistant, then ask it, in plain English:

> survey the documentation for this repo

That is the whole first run. It asks you **zero questions**, writes no project documentation, and changes
no code. It writes the decision ledger at `.docdna/manifest.json` and a one-screen `DOCDNA.md` report you
can read or hand to somebody else.

New to it? [docs/QUICKSTART.md](docs/QUICKSTART.md) walks through the same run line by line and
defines every term.

## What a first run looks like

Zero questions, because a questionnaire is what people quit.

The block below is not an illustration. It is real output, pasted unedited, from a small example
repository that ships inside this project so you can reproduce it in one line. Copy it first, because a run
writes a report into whatever it is pointed at:

```sh
cp -R tests/fixtures/internal_service /tmp/svc && python3 skill/scripts/docdna_select.py /tmp/svc
```

<!-- docdna:sample cmd="python3 skill/scripts/docdna_select.py TARGET" target="tests/fixtures/internal_service" -->
```
docdna  solo-utility  ·  335 lines Python  ·  no license  ·  CI only

Documentation  0 of 24        Leads  2 possible stale references

MISSING AND LOAD-BEARING  (22, showing 3)
  design.api-contract   Selected by iface.http. [config/urls.py]
  design.data-model     This code owns a persistent schema and the meaning of its columns lives ...
  govern.manifest       The catalog selects this document for every repository.

NOT APPLICABLE  55 documents. No compliance program exists in this repository and no external
                reviewer has been confirmed, so there is no attestation package to assemble. Full
                ledger: .docdna/manifest.json
                assure.a11y-statement is one signal away: q5_markets or q3_authorizer

NOTE            I only see documentation committed to this repo. If your docs live in Confluence or
                Notion, say so and I will mark those rows present-elsewhere rather than missing.

ASSUMED         assumed q3_authorizer=none, q2_operator=not-deployed, q5_markets=['my-org-only'].
                If a regulated relationship or external reviewer applies, up to 22 documents become
                required.

POSSIBLE STALE REFERENCES  (2)
  README.md             says `python manage.py runserver`; Procfile runs `gunicorn`; this document ...
  docs/api.md           says `11 endpoints`; 18 lines matched by the iface.http route pattern in ...
                A document may name a command without claiming this repository runs it: a comparison
                table, a task template, a case study about another repository. These are leads for a
                human to read, not findings. Full list: .docdna/manifest.json

NEXT            write 4 derivable documents  ·  refresh 1 drifted document  ·  --answer
                q3_authorizer
```

Reading it top to bottom:

- **The first line** is what docdna worked out about the project on its own: what kind of thing it is, how
  big, how it is licensed, how it is built.
- **Missing and load-bearing** is the short list that matters. Each row names the document and, in square
  brackets, the file in your code that put it on the list. You can go and look.
- **Not applicable** is the part no other tool gives you. Fifty-five documents were ruled out with a stated
  reason, and one of them is flagged as being a single answer away from becoming relevant.
- **Note** states the boundary honestly. docdna only sees documentation committed to the repository. If
  yours lives in Confluence or Notion, say so and those rows stop being reported as missing.
- **Assumed** is every guess it made, in one place, with the cost of being wrong attached. You correct it in
  one sentence rather than by filling in a form.
- **Possible stale references** are leads, not verdicts. Places where a document and the code appear to
  disagree, offered to a human to read. The heading says "possible" for a reason, and
  [docs/MEASUREMENT.md](docs/MEASUREMENT.md) publishes exactly how often these are right.
- **Next** is two or three concrete things you could do now.

Two things to hold while reading. It is a small example built on purpose, so the counts are small; a real
repository produces the same sections with larger numbers, and a few extra ones. And the sample is
regenerated and compared byte for byte by the test suite, so it cannot quietly drift from what the tool
actually prints.

## The part that earns your trust

It tells you what it did not look at.

Most tools that scan a codebase report what they found and stay silent about the rest, which leaves you
unable to tell "this does not apply here" from "we never checked". docdna prints the second category out
loud. This is real output from running it against its own repository:

<!-- docdna:sample cmd="python3 skill/scripts/docdna_scan.py TARGET" target="." section="not looked at, or refused" -->
```
not looked at, or refused
  a11y     : 2 signals unknown: gate did not fire
  ai       : 2 signals unknown: gate did not fire
  data     : 1 signals unknown: refuses to guess; ask q5_markets; resolved by q5_markets
  docs     : 1 signals unknown: refuses to guess; ask q8_doc_location; resolved by q8_doc_location
  jur      : 6 signals unknown: gate did not fire; resolved by q3_authorizer, q5_markets
  ops      : 4 signals unknown: refuses to guess; ask q6_downtime; resolved by q2_operator, q6_downtime
  sec      : 1 signals unknown: gate did not fire
  users    : 2 signals unknown: refuses to guess; ask q1_users; resolved by q1_users
```

Some rows say the check never ran. Others say docdna refused to guess and name the one question that would
settle it. **A missing answer is never recorded as "no".** A check that did not run reports `unknown`, and
`unknown` never rules a document out.

That is the difference between "we decided this does not apply" and "we did not look", and it is the only
reason the resulting ledger is worth showing to an assessor.

## Three ways to run it

| Mode | What it does | What it writes |
| --- | --- | --- |
| **Survey** (default) | Reads the code, decides the document set, reports leads | A report you can read, plus a machine-readable ledger |
| **Backfill** | Writes the documents the code can prove, with citations and marked gaps | New documents under `docs/` |
| **Check** | Re-checks documents against the code. The version you put in CI. | Updates the open-gaps summary |

Survey needs nothing at all to run. The other two run a survey first if one is missing. And if you already
know what you want, say so: "write the config reference for this repo" goes straight to writing that one
document, because being told exactly what to do should never be answered with a questionnaire.

## Invisible Unicode hygiene

Check also audits the documentation inventory for invisible Unicode that can break diffs, search, review,
or visual ordering. Every row names the file, line, column, codepoint, Unicode name, and class. Terminal
controls, bidirectional controls, and Unicode tag characters are `major`; zero-width format characters, variation selectors, and
space lookalikes are `minor`. Legitimate emoji ZWJ, VS15, and VS16 sequences are preserved. Exact totals
and class counts are retained; detailed rows are capped at 1,000 to bound report memory.

```sh
python3 skill/scripts/docdna_check.py --only hygiene /path/to/repo
```

The checker never rewrites user-authored documentation. DocDNA cleans only its generated human-facing
prose before the existing race-safe write, and it leaves manifest paths and identifiers untouched. This is
deterministic text hygiene, not statistical watermark detection, metadata removal, or evidence that a
person wrote the text.

## What it will write for you

Ten documents that are read off the code rather than reasoned about, which is why they are safe to
generate:

- how to set up and run the project locally
- a map of the codebase
- an API reference and an API contract
- a configuration reference
- a feature flag inventory
- the data model
- a glossary of project terms
- a machine-readable index for AI assistants
- a definition of done

Anything that requires human judgment is opt-in and has to be asked for by name. Runs are capped at five
documents, estimated before they start, and resumable, because a long run that dies halfway through leaves
behind exactly the confident fiction this tool exists to prevent.

The definition of done is the quiet favourite. docdna lists what your project **claims** it enforces
alongside what it can **prove** it enforces, and the gap between those two columns is the finding. Where it
cannot see the truth (branch protection rules live in your forge settings, not your code) it says so and
hands you the exact command to check for yourself.

## What it refuses to write, on purpose

The refusals are a feature. A tool that refuses nothing gets asked for everything, and then quietly makes
things up.

- **It never invents a number.** No recovery times, uptime targets, retention periods, or error budgets.
  Every one of those is a decision a person owns. Numbers are cited to a file that states them, or they are
  marked as gaps.
- **It never writes a legal instrument.** No risk assessments, no security plans, no compliance
  attestations. Seventeen of the ninety-six documents in its catalog are hard refusals enforced in code,
  not promises made in prose. Ask for one and it declines by name, explains why, and tells you which role
  has to sign it.
- **It never writes an emergency procedure.** It will write the index of which alerts have a runbook. A
  remediation step invented for somebody to follow at 03:00 is the most dangerous sentence in the catalog.
- **It never fakes a dependency list.** It detects your ecosystem and hands you the exact command that
  produces a real one. A hand-written dependency list is a lie with a filename.
- **It never touches your code.** It reports where code and documents disagree. It will not resolve that by
  editing the code.

Full detail, including the compliance posture and the three worked examples:
[docs/COMPLIANCE.md](docs/COMPLIANCE.md).

## What is proven, and what is not

This project publishes its own limits, on the grounds that a tool which overstates itself has no standing
to report anybody else's drift. Two earlier versions of this page made claims that later measurement
knocked down, so the current position is stated plainly:

- **Measured and solid.** Across 51 repositories the underlying signal layer discriminated strongly and
  never errored. What it reads genuinely varies by repository rather than emitting a constant list, which
  is the necessary condition for any of this to mean anything.
- **Not yet measured.** Nobody has independently judged whether the selected document set is *correct* for
  a given repository. There is no adjudicated sample and no measured agreement with a human expert. So
  selection ships with no accuracy percentage attached, and this paragraph stays here until somebody does
  that work.
- **Measured and modest.** The stale-reference leads are right about 3 to 11 percent of the time depending
  on the kind, which is why they are labelled leads, why they appear near the bottom of the report, and why
  they do not fail your build unless you explicitly ask them to.

The numbers, the method, and why the false positives are what they are:
[docs/MEASUREMENT.md](docs/MEASUREMENT.md).

## Compliance, briefly

The catalog carries the SOC 2, HIPAA, PCI, GDPR, EU AI Act, CRA, and ITSG-33 rows. It does not follow that
your repository owes any of them. Ninety-six entries means ninety-six rows **ruled on**, most of them not
applicable with a stated reason, not ninety-six documents written.

Three example repositories ship here, each surveyed with no questions asked:

| Example | Needed | Ruled out | HIPAA | PCI | SOC 2 |
| --- | --- | --- | --- | --- | --- |
| A plain internal web app | 41 | 55 | not applicable | not applicable | not applicable |
| One handling patient records | 35 | 61 | **optional**, data inventory recommended | not applicable | not applicable |
| One handling card payments | 33 | 63 | not applicable | **optional**, data flow recommended | not applicable |

The plain app is told it owes nothing under any of the three, and is not interrogated about them either.
SOC 2 stays quiet on all three, which is correct: SOC 2 is something an organisation elects to undergo, not
something a codebase implies.

Regulatory facts live in dated files, cited to primary sources, and CI fails when one goes stale past a
year. Full posture in [docs/COMPLIANCE.md](docs/COMPLIANCE.md).

## Does it stand alone?

Yes. docdna needs Python 3.8 on a POSIX host. Its filesystem layer checks for descriptor-relative,
no-follow primitives before using them and refuses the operation when the host cannot provide them. It
needs no third-party Python package and assumes no relationship to any other tool.
Windows is not supported because Python does not expose equivalent race-safe filesystem primitives there.

If you also use [codedna](https://github.com/hannsxpeter/codedna), which fingerprints how a repository
writes code, the two run side by side: separate projects, separate installs, no shared code, and their
instruction blocks sit in one file without touching each other. If you do not, nothing on this page
changes.

## Documentation

Start here:

- [docs/QUICKSTART.md](docs/QUICKSTART.md), a guided first run and a glossary of every term
- [docs/HOW-IT-DECIDES.md](docs/HOW-IT-DECIDES.md), how the document set is chosen, in depth
- [docs/MEASUREMENT.md](docs/MEASUREMENT.md), what has been measured about this tool and what has not
- [docs/COMPLIANCE.md](docs/COMPLIANCE.md), the compliance posture and every refusal

Deeper in:

- [skill/SKILL.md](skill/SKILL.md), the instructions your coding assistant actually follows
- [skill/catalog/SCHEMA.md](skill/catalog/SCHEMA.md), the catalog schema and its ten enforced invariants
- [skill/references/evidence.md](skill/references/evidence.md), the citation and gap rules
- [docs/AGENT_SUPPORT.md](docs/AGENT_SUPPORT.md), where it installs and what it wires up
- [CONTRIBUTING.md](CONTRIBUTING.md)

## License

MIT. See [LICENSE](LICENSE).
