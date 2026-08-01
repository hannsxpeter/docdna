# docdna: session handoff

> Written 2026-07-31 from a session that started in `~/Projects/codedna`. Project memory does not cross
> project folders, so this file carries the context over. Delete it once the repo has real docs.

## What docdna is

A portable coding-agent skill, sibling to [codedna](https://github.com/hannsxpeter/codedna). Where codedna
fingerprints a codebase's *coding style*, docdna backfills its *documentation set* from the code itself.

The defining requirement, in the user's words:

> I want to backfill documentation, based on the codebase. Of course I'd like the skill to determine which
> document is needed, not all projects require all documentation.

That second clause is the product. Generating 80 documents is easy and worthless. Deciding that this
particular repo needs 11 of them, naming which 11 and why, and saying out loud which 69 were excluded and
why, is the thing that does not exist yet.

## Decisions already made

| Question | Decision | Notes |
| --- | --- | --- |
| Addon to codedna, or its own repo? | **Own repo**, at `~/Projects/docdna` | User's call, 2026-07-31. Do not build inside the codedna repo. |
| Name | **docdna** | Verified free: GitHub under `hannsxpeter`, npm, PyPI. Only 3 same-named repos globally. |
| Layout | Mirror codedna | `skill/SKILL.md`, stdlib-only helpers in `skill/scripts/`, `install.sh`, `tests/`, MIT. |
| Wiring helper | Fork, do not share | See "Reusable from codedna" below. |

## The requirements, from the user

These came from a critique of an audience-tiered documentation taxonomy that scored about two-thirds
coverage. Both halves matter, and the structural half matters more.

### Three structural problems to solve

1. **Audience is the wrong primary axis.** Tiering by reader (exec / PM / tech lead / engineer) duplicates
   content across four parallel document sets and guarantees drift. The CTO's architecture view and the
   engineer's architecture view are the same artifact at different zoom levels, not two documents. arc42
   plus C4 handle this through viewpoints. Better primary axes: durable vs transient, or lifecycle stage,
   with audience as a secondary filter.
2. **No ADRs.** A TDD or RFC captures the debate; an ADR is the durable record of the decision. RFCs go
   stale, ADRs survive. Every important decision gets one.
3. **No document lifecycle metadata.** Nothing specifies owner, review cadence, status
   (draft / active / superseded), or retirement. This is what actually kills documentation sets, more
   often than missing document types do.

Two smaller notes: "RFC" here means Request for Comments, but in any ITSM shop it reads as Request for
Change, so disambiguate. And nothing ties business case to PRD to epic to story to test case to release to
post-mortem. Without that traceability spine it is a list, not a system.

### Seven categories most taxonomies miss entirely

1. **Quality and test.** Test strategy, test plans, requirements traceability matrix, UAT plan and sign-off,
   performance and load reports, operational acceptance testing evidence, defect management process,
   Definition of Ready, Definition of Done. The RTM in particular is what lets a stakeholder see at sign-off
   exactly which requirements are verified and which defects remain open.
2. **Security, privacy, and compliance.** The largest hole. STRIDE threat model, secure design review, SBOM,
   SAST and SCA scan evidence, vulnerability disclosure and response policy, penetration test reports,
   secrets management policy, RBAC and access matrix, data classification, PIA and DPIA, security incident
   response plan (distinct from ops runbooks). NIST SP 800-218 organizes these into Prepare, Protect,
   Produce, Respond, and procurement teams now routinely request SSDF attestations alongside SBOMs. For this
   user specifically: the SA&A package, ITSG-33 control profile traceability, and the authority-to-operate
   evidence chain.
3. **Operational readiness and service transition.** Runbooks and SLOs exist in most lists, but no gate that
   says operations agreed to accept the thing. Missing: service design package, operational readiness review
   and go/no-go, support model and escalation matrix, on-call arrangements, CMDB and service catalogue
   entry, DR and BCP with RTO and RPO, backup and restore procedures, capacity plan, hypercare plan, known
   error database, decommissioning plan.
4. **Design, UX, and accessibility.** User research, journey maps, information architecture, design system
   and tokens, usability test reports, accessibility conformance. That last one is not optional here:
   Government of Canada procurement requires an Accessibility Conformance Report based on the latest VPAT,
   assessed against EN 301 549 (2021), which includes WCAG 2.1 AA.
5. **Everything customer-facing.** Release notes, changelog, user guides, knowledge base articles, API
   developer portal, migration guides, training materials, support macros. Diataxis is the organizing model:
   tutorials, how-to guides, reference, explanation, each serving a distinct need.
6. **Data and AI governance.** Data contracts (versioned, enforceable producer-consumer agreements
   specifying schema, freshness, quality, and breaking-change policy), lineage, classification, retention.
   And for anything with a model in it: model cards, system cards, dataset cards, eval reports, AI risk
   register. EU AI Act Annex IV and NIST SP 800-218A apply.
7. **Agent context files as an artifact class.** AGENTS.md, CLAUDE.md, SKILL.md. Most taxonomies nod at AI
   assistants without treating their context files as documents with owners and review cadences.

Also thin and worth catalog entries: RAID log (most lists have only the R), decision log, RACI, stakeholder
register, communication plan, contracts and SOW, OSS license attribution, contractual SLAs as distinct from
SLOs, vendor risk assessments, benefits realization review, tech debt register, OCM and adoption plan.

### One warning carried over

The source taxonomy had embedded examples (Rust audio buffers, anti-detect scraping, smart contract proxy
signing) that were leftover context from whatever produced the draft. In a reusable reference they confuse
readers who do not share that context. Keep docdna's examples generic or drawn from the repo under analysis.

## Reusable from codedna

Read `~/Projects/codedna` directly. The parts that matter:

- **`skill/scripts/codedna_wire.py` is nearly generic already.** Only three things are codedna-specific: the
  `<!-- codedna:start -->` / `<!-- codedna:end -->` markers, the `PLAIN_BLOCK` text, and the
  `.cursor/rules/codedna.mdc` filename. Everything else (`existing_targets` discovery, `replace_block`
  idempotency, `write_target`, the Cursor and Cascade frontmatter handling, the `--agent` / `--all` / `--json`
  CLI) transfers as-is. Fork it to `docdna_wire.py` with new markers rather than trying to share one file
  across two repos.
- **`install.sh`** transfers with the skill name swapped. It resolves `VERSION` by grepping
  `^Version: ` out of `skill/SKILL.md`, supports `all|claude|codex|cursor|windsurf`, honours
  `*_SKILLS_DIR` env overrides, and cleans up stale bare-file installs. Reuse the shape exactly.
- **`skill/scripts/codedna_stats.py`** has tree-walking, language detection, and skip/cap logic that a
  documentation signal scanner needs too. Worth reading before writing docdna's scanner from scratch.
- **The SKILL.md voice.** codedna's prose is terse, second person, imperative, heavy on the "X, not Y"
  construction, bold lead-ins on list items, real snippets over description, and tables where a table
  earns its place. Match it so the two read as one family. Note the house rule: no em dashes, no en dashes,
  no emojis, anywhere.
- **Structural lesson from codedna's v1.0.0 audit:** bare `.md` files in `~/.claude/skills/` are NOT loaded
  by Claude Code. The correct format is `~/.claude/skills/<name>/SKILL.md`. Do not repeat that mistake.

## The design spec

**`DOCDNA-DESIGN.md`, beside this file. Read it first. It supersedes this handoff wherever they differ.**

A 12-agent research and design pass produced it: current standards (arc42, C4, MADR, Diataxis,
ISO/IEC/IEEE 42010, ITIL 4), compliance regimes with 2026 currency checks (NIST SSDF, EU AI Act Annex IV
timing, EU CRA, EN 301 549, ITSG-33 and GC SA&A), overlap with the user's installed skills, then three
critique passes (adversarial, completeness, product) folded back in. 1,311 lines, 14 sections, including a
"rejected critiques" section that records what did not land and why.

### How docdna is positioned against the user's own tools

The prior-art pass found the overlap is real but splits cleanly, and this is the positioning:

- **`godpowers`** already does doc-set *selection*: `references/building/DOCUMENTATION-PROFILE.md`, a 17-row
  by 4-scale matrix modified by product form, risk, and regulatory overlay, tagging each document
  `required | recommended | optional | not-applicable` with the reason. But it runs at **plan time from
  intake answers**, not by reading existing code.
- **`godaudits`** already does gap *detection*: check `A-REPO-24` reads a repo, infers form/scale/risk, and
  names the missing profile-required docs. But it is `audit_only` and **never writes a document**.

Nobody closes the loop between them. And nothing in the installed collection does document **lifecycle
metadata**, the **traceability spine**, or the **regulated and GC categories**. Those were the user's three
structural complaints, and they are genuinely unclaimed.

docdna's line: *godpowers decides before code exists, godaudits reports the gap, docdna reads the code and
fills it.* Standalone and portable like codedna, interoperating with the profile format rather than
reinventing it.

### Settled

- **Name is `docdna`.** The user confirmed it on 2026-07-31. Spec section 13 open question 1 offers
  `docdebt` as an alternative with a cleaner namespace; that question is **closed, do not reopen it**.
- Two repos, two skills. Driven by listing economics, not taste: Claude Code caps each skill description at
  1536 characters and evicts descriptions when the listing overflows. This user runs 121 skills at 31,795
  description chars with a dozen already name-only. A merged description would truncate mid-sentence.
  Both descriptions come down to roughly 400 characters.
- Artifact is `DOCDNA.md` plus a canonical `.docdna/manifest.json`.
- Modes: **Survey** (default), **Backfill**, **Check**. No Refresh mode, that is Check then scoped Backfill.
- Catalog: 159 entries across ten lifecycle stages. Only **41 carry a template**, 102 are manifest-only, and
  16 are `producible: refuse` (legal instruments docdna never drafts). The catalog is a ledger, not a
  generator.
- Eight archetypes plus ten additive overlays. Eight interview questions, **zero asked on the first run**,
  every answer defaulted from signals and labelled `assumed`.
- v0.1 is **Survey only**: `docdna_scan.py`, a 61-row catalog, `docdna_select.py`. No Backfill, no Check,
  no wiring, no templates.

### Still open, needs the user

Spec section 13 lists seven. These four actually matter:

1. **The headline job.** The spec pitches **handover** and treats compliance as the depth behind it, which
   inverts the original GC-led framing. Handover is universal and self-serving; audit prep is rare and
   coerced. If the near-term need really is GC delivery work, the README leads differently. The machinery
   does not change either way.
2. **Who maintains the regime files, at what cadence?** Six files of dated regulatory facts is a standing
   commitment, and quarterly is the proposal. If the honest answer is "nobody", cut to three (EU, Canada,
   standards) and permanently demote the jurisdiction overlays to hints.
3. **Two Canadian claims must be re-verified by a human before they ship as assertions.** Neither could be
   confirmed by automated fetch, because the TBS pages bot-block: the data-classification anchor (ITSG-33
   Annex 1 plus the TBS Directive on Security Management), and the AIA level-to-requirement matrix
   (Appendix C of the Directive on Automated Decision-Making). Until confirmed, both stay out of
   `regime-facts/canada.md`. Do not let these ship on inference.
4. **codedna 1.0.3 before or with docdna 0.1?** Before is cleaner. It narrows codedna's description and
   parameterizes `replace_block`.

   One correction to the spec on this point. The spec calls the `replace_block` signature "a latent clobber
   bug today". Verified against the source, and that overstates it: `START` and `END` are module constants
   and codedna always pairs them with its own `PLAIN_BLOCK`, so standalone codedna has no live defect. The
   real hazard is the **fork**. Copy `codedna_wire.py` to `docdna_wire.py`, change `PLAIN_BLOCK`, and forget
   the two module constants, and `replace_block` will happily find the codedna markers and overwrite the
   codedna block with docdna's. Threading `start` and `end` as parameters is worth doing because it makes
   that mistake impossible, not because anything is broken now.
