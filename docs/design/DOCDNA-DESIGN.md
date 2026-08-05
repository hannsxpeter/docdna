# docdna: consolidated design spec

Version 0.1 draft. Written 2026-07-31. Supersedes the three prior design documents and folds in all three critiques.

This is the document an implementer builds from. Where the prior designs disagreed, this one picks. Where a critique landed, the fix is folded in and marked. Where a critique was wrong, section 14 says so.

---

## 1. Verdict: packaging and name

**Two skills, two repositories, and the new one is called `docdna`.** The listing economics settle the skill count: Claude Code reserves roughly one percent of context for the skill listing, drops descriptions for least-used skills when it overflows, and caps each description at 1536 characters. This user's environment already runs 121 skills and 31,795 description characters, and a dozen skills are already listed name-only. A merged codedna-plus-docdna description would exceed the per-skill cap and get truncated mid-sentence, silently amputating one of the two jobs; two entries at 400 characters each survive. The repository count is settled by maintenance half-life, not by release engineering: codedna's content is about naming conventions and comment density and does not expire, while docdna's regime references carry dated regulatory claims that rot in two quarters. Coupling them drags codedna's clean single-product changelog onto a regulatory treadmill, and `install.sh` deriving `VERSION` from one `SKILL.md` makes the fork cheaper than the generalization at N equals two. The name is `docdna` and the artifact is `DOCDNA.md`: the metaphor is a stretch and the search neighborhood is crowded with document-AI products, but a new skill is listed name-only on install day, so the name is the trigger, and a user who owns `codedna` will guess `docdna` and type it verbatim. `DOCSDNA` never appears anywhere; it collides with a live commercial product and it contradicts itself across the prior designs. Revisit a monorepo at skill number three, not before.

Consequences that ship in the same change:

- codedna goes to **1.0.3**: description narrowed to roughly 420 characters, one closing sentence pointing project-documentation requests at docdna, and `replace_block` gains threaded `start`/`end` parameters so a caller passing a different block cannot clobber the codedna markers. One `### Changed` line in the changelog.
- Markers, rule basenames, and artifact names are disjoint by construction: `<!-- docdna:start -->`, `.cursor/rules/docdna.mdc`, `.devin/rules/docdna.md`, `DOCDNA.md`. Both blocks present in one `AGENTS.md` is the expected steady state and there is a fixture for it.
- `codedna_wire.py` and `docdna_wire.py` share a body and a `wire_targets.json` data file. No sha256 pinning, no cross-repo CI ritual. One line in each `CONTRIBUTING.md`: if you change the agent target table, change it in the sibling repo too.

**Both READMEs carry the same strapline above the fold:** *Derived from the code. Nothing asserted that the repo cannot prove.* That is the family. "DNA" is the surname, not the thesis. Cross-link under "See also", not under a suite page. Do not build a suite.

---

## 2. What this is, and why it is not any of the user's existing skills

Documentation lies. Not by malice; by drift. The README says `npm run dev` and the script was renamed fourteen months ago. The API doc lists eleven endpoints and the router registers twenty-three. The threat model was written before the service went multi-tenant. Meanwhile the documents that would actually survive an audit, a handover, or a departure were never written at all, because nobody could say which ones this particular project owes.

docdna answers three questions from the code: **which documents does this project owe, which of the ones you have are now false, and what does the code let me write without asking anyone.** It is a selection engine and a drift detector first, a generator third.

**The one-sentence positioning:** the documentation profile, derived from code instead of from an intake questionnaire, with a lifecycle and a drift test.

### Why not an existing skill

The user has 121 skills installed. Five are close. None of them do this.

| Neighbour | Owns | Does not do |
|---|---|---|
| `DOCUMENTATION-PROFILE.md` (godpowers) | Doc-set selection: scale baseline times product form times risk overlay, with required/recommended/optional/not-applicable and the signal that set it | Runs at plan time from intake answers. Never reads an existing repo. Never writes a document. |
| `godaudits` `A-REPO-24` | Detects on a real repo that the doc set does not match the profile | Reports. Never writes. Never selects; it consumes a profile someone else made. |
| `gsd-docs-update` | Writes nine developer docs, verified against the codebase | Selects from three booleans. Taxonomy is developer onboarding only: no governance, quality, security, service transition, accessibility, customer-facing, or data and AI documents. |
| `repo-ready` | README, CONTRIBUTING, SECURITY.md, CHANGELOG, ADR scaffolding, and a type-by-stage-by-audience matrix | Stops at the repo boundary. No compliance evidence, no service transition, no customer-facing set. |
| `architecture-ready`, `harden-ready`, `observe-ready` | ADRs, arc42, C4; threat models and disclosure; runbooks and SLOs | Each owns one family. None produces a manifest. None reconciles across families. |

**Four things nobody does, in descending order of defensibility:**

1. **It closes detect, decide, write on a brownfield repo.** godpowers decides from intake. godaudits detects and reports. gsd writes nine docs from three booleans. Nothing derives the profile from code and then fills the gap.
2. **It detects drift with zero adoption.** Command strings in any markdown file checked against `package.json` scripts, `Makefile` targets, and CI steps. Paths mentioned in docs checked for existence. Endpoint lists diffed against detected routes. Doc last-commit versus code last-commit. None of that needs frontmatter, a manifest, or an interview. It is the cheapest high-value output in the design and it works on documents docdna has never touched.
3. **It carries document lifecycle metadata as a first-class output, and expires its own exclusions.** `revisit_when` is the single novel idea here. No documentation framework, no compliance tool, and no auditor skill tells you when a document you correctly skipped last year became required. That converts a one-time generation into a standing guarantee.
4. **It covers the categories nobody has as documents rather than findings:** ITIL service transition, Canadian ITSG-33 and SA&A evidence indexing, RAID as an artifact, Diataxis-structured customer-facing docs, and accessibility conformance inputs.

**Ownership rule, stated once and enforced everywhere.** docdna owns the manifest. It does not own every document in it. A catalog entry may name another skill as owner, in which case docdna writes a pointer and a manifest row and no file. Ship as an integrator, not a competitor.

### The buyer

The buyer is a tech lead, staff engineer, delivery manager, or consultant, not the individual developer who buys codedna. The trigger moment is external pressure: a handover, an audit, a procurement questionnaire, an onboarding, a departure. **The headline job is handover, not compliance.** Everybody leaves a project; "I am rolling off in three weeks, what has to be written down" is a question every senior engineer asks and nothing answers. It uses the same machinery, targets a person with autonomy and no procurement cycle, and is the on-ramp to the audit case later. Compliance is the depth. Handover is the pitch.

---

## 3. Modes

Three modes. Structurally parallel to Map, Match, Check, without reusing the verbs.

| Mode | What it does | Writes | Cost |
|---|---|---|---|
| **Survey** (default) | Scan, detect signals, detect drift in documents that already exist, decide the doc set, write the manifest. Writes no documents. | `.docdna/manifest.json`, `DOCDNA.md` | Under 15 seconds |
| **Backfill** | Generate selected documents from code evidence, with citations and GAP markers. Bounded, resumable, estimated up front. | `docs/**`, updates the manifest | Minutes per document |
| **Check** | Deep drift, frontmatter lint, GAP rollup, spine coverage, stale exclusions. The CI gate. | Nothing | Seconds |

### Routing

Read the user's intent and pick one. Three rules, in order:

1. **A request naming a single document routes straight to Backfill for that document.** "Write the threat model for this repo" is maximum intent and must not be met with a questionnaire. Write the manifest row as a side effect.
2. **Survey requires nothing.** No `DOCDNA.md`, no answers, no prior run.
3. **Backfill and Check run Survey first if `.docdna/manifest.json` is absent**, silently, and continue.

### Why no Refresh mode

Refresh is Check followed by Backfill scoped to what Check flagged. It is a composition, not a capability, and a second mode would mean two code paths that must agree about what stale means; they will not. Staleness lives inside Check, loudly: Check leads with the drift ledger and `docdna_check.py` exits nonzero on a gated finding.

### Why Check is not called Audit

The user's environment already runs seven `*auditor` skills plus `godaudits`. Naming a mode Audit is a trigger-accuracy self-injury.

---

## 4. The lifecycle-stage document catalog

### 4.1 The primary axis is durability. The organizing axis is lifecycle stage.

Audience is not a partition and never was. ISO/IEC/IEEE 42010:2022 settles it: audience is stakeholder plus concern, the document set is partitioned by viewpoint, and cross-audience consistency is a correspondence rule, not a parallel tree. The CTO's architecture view and the engineer's architecture view are the Building Block View at whitebox level 1 and level 3. One artifact, two zoom levels.

Every entry carries `audiences: []`. **v1.0 ships no audience renderer.** The array exists so the data is there when someone asks; building a projection nobody has requested is exactly the theater this skill refuses.

**Durability, three values.** The requested durable-versus-transient split is one value short, because compliance evidence is never updated (like transient) and must be retained for a legally fixed period (unlike transient).

| Code | Value | Update contract | Backfill posture |
|---|---|---|---|
| `DUR` | durable | Edited in place; `last_reviewed` bumped | Backfill these. This is the product. |
| `EVI` | evidence | Never edited. A new run produces a new dated file. | Backfill the index and the inputs. Never the evidence itself. |
| `TRA` | transient | Written once, dated, abandoned | Never generated. See 4.6. |

**Lifecycle stage, ten values.** A document belongs to the stage at which it first becomes load-bearing, not the stage in which it is most often read. Each stage answers exactly one question.

| Stage | Question it answers |
|---|---|
| `frame` | Why does this exist, for whom, and what counts as success? |
| `decide` | What did we choose, and what did we reject? |
| `design` | What shape is it, and why that shape? |
| `build` | How do I work on it? |
| `verify` | How do we know it works? |
| `assure` | How do we prove to an outsider it is safe, lawful, and accessible? |
| `operate` | How do we run it and keep it alive? |
| `serve` | How does someone use it? |
| `govern` | How is the work itself managed? |
| `retire` | How does it end? |

The stage list is an ordering of first authorship, not a waterfall. A backfilled repo will have `build` and `operate` documents long before anyone writes the `frame` documents. The manifest must not scold the user for that.

### 4.2 The three fields that resolve the critiques

**`producible`.** The adversarial critique is right that sixteen entries can never be written under the skill's own rules and yet the prior design shipped templates for them. The completeness critique is right that ~28 more document classes are missing. Both are resolved by one field, not by cutting or growing the catalog.

| Value | Meaning | Ships a template |
|---|---|---|
| `Y` | docdna writes it from code evidence | Yes |
| `M` | manifest-only. docdna names it, rules on it, assigns an owner candidate, and states what a human must produce. No file is created. | No |
| `R` | **refuse.** A legal declaration or regulator-facing instrument. docdna never emits it and never reproduces its section structure, because structural fidelity is precisely what makes a draft submittable. It emits a differently-named evidence annex under `docs/assure/inputs/` and a named list of who must sign. | No, and `docdna_select.py` errors if a template exists for an `R` entry |

**A template that exists will be filled, because a slot is an invitation.** That is why `M` and `R` ship no template, and why the split is enforced in code and not in prose.

**`scope`.** Roughly seventeen entries are organizational, not repo-level. Emitting them into every repo produces N drifting copies of one policy, which is the duplication failure the durability axis eliminated, re-created on a different axis.

| Value | Meaning |
|---|---|
| `R` | repo-level. Lives with this code. |
| `P` | product-level. One per deployed system, which may span repos. |
| `O` | org-level. One per organization. docdna emits a pointer row with `inherits_from`, never a copy. |

Every `P` and `O` entry defaults `system_of_record: ask`, which is the fix for the modal enterprise failure: reporting "absent" for a document that exists in Confluence, GCdocs, or ServiceNow. One false absence in front of an assessor destroys trust in the whole manifest.

**`satisfies`.** The deduplication axis, and the most important idea in the catalog. A threat model is simultaneously SSDF PW.1.1, ISO 27001 A.8.27, CRA Annex I Part I, and an ITSG-33 TRA. Four regimes, one artifact, four bindings. Without it, a regulated project gets four near-copies that drift within a quarter. The same holds for the SBOM, the vulnerability disclosure policy, the impact assessment family, the accessibility conformance report, and the secure coding standard.

### 4.3 Column key

`D` durability (DUR/EVI/TRA) · `Sc` scope (R/P/O) · `Pr` producible (Y/M/R) · `BF` backfillability (H high, P partial, N none) · `Cad` review cadence (RN none, RM 30d, RQ 90d, RS 180d, RA 365d, R3 1095d, RE on-release, RC on-change)

Paths are repo-relative defaults and are overridable in `.docdna/config.json`. `Selects on` is the terse form of the rule predicate; the normative predicate lives in `catalog/rules.json`.

### 4.4 The catalog

#### Stage 1: frame (11)

| id | Document | D | Sc | Pr | BF | Cad | Selects on | Satisfies |
|---|---|---|---|---|---|---|---|---|
| `frame.business-case` | Business case | DUR | P | M | N | RA | `scale>=funded` | |
| `frame.vision` | Vision and strategy | DUR | P | M | N | RA | `scale>=internal` | |
| `frame.requirements` | Requirements specification (PRD/SRS) | DUR | P | Y | P | RS | `always` | `iso29148` |
| `frame.user-research` | User research and personas | DUR | P | M | N | RA | `users.ui` | |
| `frame.stakeholders` | Stakeholder register | DUR | P | Y | P | RS | `scale>=internal` | `arc42:1` |
| `frame.success-metrics` | Success metrics | DUR | P | M | P | RQ | `scale>=internal` | |
| `frame.scope` | Scope and boundaries | DUR | P | Y | P | RS | `always` | `arc42:3` |
| `frame.roadmap` | Roadmap | DUR | P | M | P | RQ | `scale>=funded` | |
| `frame.glossary` | Glossary | DUR | R | Y | H | RS | `always` | `arc42:12` |
| `frame.comms-plan` | Communication plan | DUR | O | M | N | RA | `scale>=enterprise` | |
| `frame.adoption-plan` | Change and adoption plan | DUR | P | M | N | RS | `scale>=enterprise \|\| jur.gc` | |

#### Stage 2: decide (6)

| id | Document | D | Sc | Pr | BF | Cad | Selects on | Satisfies |
|---|---|---|---|---|---|---|---|---|
| `decide.adr` | Architecture decision record | DUR | R | Y | P | RN | `always` | `arc42:9` |
| `decide.adr-index` | Decision index | DUR | R | Y | H | RC | `decide.adr present` | `arc42:9` |
| `decide.design-proposal` | Design proposal (never `rfc/`) | TRA | R | M | N | RN | `multi_team \|\| scale>=funded` | |
| `decide.spike` | Spike findings | TRA | R | M | N | RN | `never` (pointer only) | |
| `decide.change-record` | Change record index (ITSM RFC) | EVI | P | M | P | RN | `has_service && (scale>=enterprise \|\| jur.gc)` | `itil:change-enablement` |
| `decide.waivers` | Exception and risk acceptance register | DUR | R | Y | P | RQ | `has_deps` | |

`decide.adr` absorbs `decision-log` and `tech-selection`. The critique lists "no ADRs" and "decision log missing" as two gaps; they are one gap. Do not generate both.

#### Stage 3: design (13)

| id | Document | D | Sc | Pr | BF | Cad | Selects on | Satisfies |
|---|---|---|---|---|---|---|---|---|
| `design.architecture` | Architecture description (arc42) | DUR | P | Y | P | RS | `always`, depth by scale | `arc42`, `iso42010` |
| `design.diagrams` | C4 context and container diagrams | DUR | P | Y | H | RS | `has_service \|\| multi_team` | `c4` |
| `design.quality-scenarios` | Quality requirements | DUR | P | M | P | RS | `scale>=funded` | `arc42:10` |
| `design.data-model` | Data model and dictionary | DUR | R | Y | H | RC | `data.schema` | |
| `design.api-contract` | API contract (OpenAPI/proto/SDL) | DUR | R | Y | H | RC | `iface.http \|\| iface.grpc \|\| iface.graphql` | |
| `design.integrations` | Integration and interface catalogue | DUR | P | Y | H | RQ | `has_service` | |
| `design.data-contract` | Data contract | DUR | P | M | P | RQ | `data.pipeline` | `odcs:3.1.0` |
| `design.journeys` | Journey map | DUR | P | M | P | RA | `users.ui` | |
| `design.ia` | Information architecture | DUR | P | M | H | RA | `users.ui` | |
| `design.design-system` | Design system and tokens | DUR | P | M | H | RQ | `users.ui && scale>=funded` | |
| `design.ui-spec` | Screen register | DUR | P | M | P | RS | `users.ui` | |
| `design.content-style` | Content and voice guide | DUR | O | M | P | RA | `users.external && scale>=funded` | `diataxis` |
| `design.usability-report` | Usability test report | EVI | P | R | N | RN | `users.ui && scale>=funded` | `iso9241-11` |

#### Stage 4: build (19)

| id | Document | D | Sc | Pr | BF | Cad | Selects on | Satisfies |
|---|---|---|---|---|---|---|---|---|
| `build.readme` | README | DUR | R | M | H | RC | `always` | defers `repo-ready` |
| `build.contributing` | Contributing guide | DUR | R | M | H | RS | `is_oss \|\| multi_team` | defers `repo-ready` |
| `build.dev-setup` | Development setup | DUR | R | **Y** | H | RC | `always` | `diataxis:how-to` |
| `build.codebase-map` | Codebase map | DUR | R | **Y** | H | RC | `scale>=internal` | |
| `build.coding-standard` | Coding standard (incl. secure coding) | DUR | O | Y | H | RA | `always` | `ssdf:PW.5.1`, `iso27001:A.8.28`, `soc2:CC8.1` |
| `build.codedna` | Style fingerprint | DUR | R | M | H | RS | `always` | defers `codedna` |
| `build.api-reference` | API reference (generated) | DUR | R | **Y** | H | RC | `iface.* \|\| is_oss` | `diataxis:reference` |
| `build.config-reference` | Configuration reference | DUR | R | **Y** | H | RC | `has_service` | `diataxis:reference` |
| `build.release-process` | Build and release engineering | DUR | R | Y | H | RC | `has_release_process` | `ssdf:PS.2`, `ssdf:PS.3` |
| `build.dependency-policy` | Dependency policy | DUR | O | M | P | RA | `has_deps` | `ssdf:PW.4.1`, `iso27001:A.8.30` |
| `build.migrations` | Schema migration procedure | DUR | R | Y | H | RC | `data.migrations` | |
| `build.feature-flags` | Feature flag register | DUR | R | **Y** | H | RM | `ops.flags` | |
| `build.agents-md` | AGENTS.md | DUR | R | Y | P | RC | `always` | `agentsmd` |
| `build.agent-host-rules` | Host-specific agent rules | DUR | R | Y | H | RC | `docs.agent_files \|\| opt-in` | |
| `build.skill-md` | SKILL.md | DUR | R | M | P | RS | `arch.agent_skill` | `agentskills` |
| `build.llms-txt` | Agent documentation index | DUR | R | **Y** | H | RC | `is_oss \|\| users.external` | `llmstxt` |
| `build.model-card` | Model card | DUR | P | M | P | RS | `ai.weights \|\| ai.training` | `aiact:annexXI` |
| `build.dataset-card` | Dataset card | DUR | P | M | P | RS | `data.pipeline \|\| ai.training_data` | `aiact:annexIV.2d` |
| `build.compat-matrix` | Host and platform compatibility matrix | DUR | R | Y | H | RE | `arch.agent_skill \|\| ships_artifact` | |

The six **Y** entries in bold above, plus `design.data-model`, `design.api-contract`, `frame.glossary`, and `verify.dod`, are the **derivable ten**: the default Backfill target. They are near-zero hallucination risk, cheap, and genuinely useful.

#### Stage 5: verify (12)

| id | Document | D | Sc | Pr | BF | Cad | Selects on | Satisfies |
|---|---|---|---|---|---|---|---|---|
| `verify.test-strategy` | Test strategy | DUR | P | Y | P | RA | `scale>=funded` | `iso29119-3` |
| `verify.test-plan` | Test plan | DUR | P | M | P | RE | `scale>=funded` | `iso29119-3` |
| `verify.rtm` | Requirements traceability matrix | DUR | P | Y | P | RC | `scale>=funded \|\| regulated` | `iso29148` |
| `verify.uat` | UAT plan and sign-off | EVI | P | R | P | RN | `users.external && scale>=funded` | `iso29119` |
| `verify.perf-report` | Performance and load test report | EVI | P | M | P | RN | `has_service && scale>=funded` | |
| `verify.oat` | Operational acceptance evidence | EVI | P | M | P | RN | `has_service && operated_by_others` | `itil:svt` |
| `verify.completion-report` | Test completion report | EVI | P | M | H | RE | `has_release_process && scale>=funded` | `iso29119-3` |
| `verify.coverage` | Coverage evidence | EVI | R | M | H | RE | `qual.coverage_tooling` | |
| `verify.defect-process` | Defect management process | DUR | O | M | P | RA | `scale>=internal` | `ssdf:RV.2`, `itil:problem` |
| `verify.dod` | Definition of Ready / Definition of Done | DUR | R | **Y** | H | RS | `multi_team \|\| scale>=funded` | `ssdf:PO.4.1` |
| `verify.ai-eval` | AI evaluation report | EVI | P | M | P | RQ | `ai.present` | `aiact:annexIV.2h`, `nist-airmf:MEASURE` |
| `verify.data-quality` | Data quality and validation report | EVI | P | M | P | RQ | `data.pipeline \|\| ai.training_data` | `aiact:art10` |

`verify.dod` is the highest-value entry in this stage and is in the derivable ten by exception: the Definition of Done that is **actually enforced** is derivable from required CI checks, branch protection, PR template checklists, merge queue config, and required reviewers. Emit enforced-versus-claimed as two columns. The gap is the finding.

#### Stage 6: assure (39)

Twenty-one of these are `M` and thirteen are `R`. Five are `Y`. That ratio is the point.

| id | Document | D | Sc | Pr | BF | Cad | Selects on | Satisfies |
|---|---|---|---|---|---|---|---|---|
| `assure.secure-sdlc-policy` | Secure development policy | DUR | O | M | P | RA | `Q3 != none` | `ssdf:PO.1`, `iso27001:A.8.25` |
| `assure.threat-model` | Threat model | DUR | P | M | P | RS | `sec.authn \|\| data.pii \|\| has_service` | `ssdf:PW.1.1`, `iso27001:A.8.27`, `cra:annexI.I`, `itsg33:TRA` |
| `assure.attack-surface` | Attack surface inventory (threat model input) | DUR | P | **Y** | H | RS | same as above | input to `assure.threat-model` |
| `assure.secure-design-review` | Secure design review record | EVI | P | R | N | RN | `scale>=enterprise \|\| regulated` | `ssdf:PW.2.1` |
| `assure.sbom` | Software bill of materials | EVI | R | Y | H | RE | `has_deps` | `cisa-sbom:2026`, `cra:annexVII.2b` |
| `assure.license-attribution` | OSS attribution notice | EVI | R | M | H | RE | `has_deps && (is_oss \|\| ships_artifact)` | `spdx` |
| `assure.scanning-index` | SAST and SCA evidence index | EVI | R | **Y** | H | RE | `sec.scanners \|\| regulated` | `ssdf:PW.7`, `ssdf:PW.4.4` |
| `assure.pentest` | Penetration test report | EVI | P | R | N | RA | `scale>=enterprise \|\| Q3 in {auditor, gov}` | `ssdf:PW.8` |
| `assure.vdp` | Vulnerability disclosure policy | DUR | O | M | H | RA | `is_oss \|\| ships_artifact \|\| jur.eu \|\| jur.us_fed` | `ssdf:RV.1.3`, `cra:art13.8`, `iso29147` |
| `assure.vuln-handling` | Vulnerability handling process | DUR | O | M | P | RA | `ships_artifact \|\| is_oss \|\| jur.eu` | `ssdf:RV.1`, `iso30111`, `cra:art14` |
| `assure.secrets-policy` | Secrets management policy | DUR | O | M | P | RA | `has_service \|\| sec.authn` | `ssdf:PS.1`, `iso27001:A.8.24` |
| `assure.key-management` | Key management and rotation procedure | DUR | O | M | P | RA | `sec.signing \|\| sec.crypto` | `iso27001:A.8.24` |
| `assure.crypto-inventory` | Cryptographic inventory and PQC plan | DUR | P | M | P | RA | `sec.crypto && (jur.us_fed \|\| jur.gc)` | `cnsa2`, `cbom` |
| `assure.rbac-matrix` | Access control inventory | DUR | P | M | P | RS | `sec.authn` | `iso27001:A.5.15`, `itsg33:AC` |
| `assure.identity-lifecycle` | Joiner/mover/leaver and privileged access | DUR | O | M | N | RA | `sec.authn && scale>=funded` | `soc2:CC6.2`, `iso27001:A.5.16` |
| `assure.audit-logging` | Audit logging and retention standard | DUR | P | M | P | RA | `sec.authn \|\| data.pii` | `iso27001:A.8.15`, `soc2:CC7.2` |
| `assure.hardening-baseline` | Configuration hardening baseline | DUR | P | M | P | RA | `deploy.iac \|\| deploy.container` | `iso27001:A.8.9`, `soc2:CC6.6`, `itsg33:CM` |
| `assure.data-classification` | Data classification and retention register | DUR | P | M | P | RA | `data.pii \|\| data.pipeline \|\| jur.gc` | `iso27001:5.33`, `nist80053:SI-12` |
| `assure.ropa` | Records of processing activities | DUR | P | M | P | RA | `data.pii && jur.eu` | `gdpr:art30` |
| `assure.privacy-notice` | Public privacy notice | DUR | P | M | P | RA | `data.pii && users.external` | `gdpr:art13`, `pipeda:p8` |
| `assure.dpa-subprocessors` | DPA and subprocessor list | DUR | O | M | P | RA | `users.external && data.pii` | `gdpr:art28` |
| `assure.build-provenance` | Build provenance and signing | EVI | R | M | H | RE | `ships_artifact` | `ssdf:PS.2`, `slsa` |
| `assure.supplier-reqs` | Supplier security requirements | DUR | O | M | N | RA | `scale>=enterprise \|\| Q3 in {gov, auditor}` | `ssdf:PO.1.3`, `iso27001:A.5.19` |
| `assure.vendor-risk` | Vendor risk assessment | EVI | O | M | P | RA | `has_service && scale>=funded` | `iso27001:A.5.19` |
| `assure.training-records` | Training records | EVI | O | R | N | R3 | `regulated \|\| jur.gc` | `ssdf:PO.2.2`, `sor2025-255` |
| `assure.sec-incident-plan` | Security incident response plan | DUR | O | M | P | RA | `data.pii \|\| (has_service && scale>=funded)` | `iso27001:A.5.24`, `gdpr:art33`, `cra:art14` |
| `assure.control-mapping` | Control framework mapping register | DUR | P | **Y** | P | RS | `Q3 != none` | `ssdf`, `iso27001`, `iso42001`, `soc2`, `itsg33:annex3a` |
| `assure.control-inheritance` | Cloud control inheritance / CRM | DUR | P | M | P | RA | `deploy.cloud && Q3 in {gov, auditor}` | `fedramp:crm`, `itsg33` |
| `assure.saa-inputs` | SA&A evidence index (never an SSP) | EVI | P | R | P | RA | `jur.gc && Q3 == gov` | `itsg33`, `tbs:dsm` |
| `assure.ato` | Authority to operate | EVI | P | R | N | RA | `jur.gc && Q3 == gov` | `tbs:dsm` |
| `assure.impact-screening` | Impact assessment screening (DPIA/PIA/FRIA/AIA) | EVI | P | R | P | RA | `Q4 != no`, jurisdiction-gated | `gdpr:art35`, `tbs:pia`, `aiact:art27`, `tbs:aia`, `iso42005` |
| `assure.cra-technical-file` | CRA technical documentation | EVI | P | R | P | RE | `jur.eu && (ships_artifact \|\| arch.firmware)` | `cra:annexVII` |
| `assure.eu-doc` | EU declaration of conformity | EVI | P | R | N | RE | `jur.eu && ships_artifact` | `cra:annexV`, `aiact:art47` |
| `assure.aiact-annex4` | AI Act technical documentation | EVI | P | R | P | RA | `ai.present && annex_iii_domain` | `aiact:art11`, `aiact:annexIV` |
| `assure.gpai-docs` | GPAI model documentation | EVI | P | R | P | RA | `ai.gpai_provider` | `aiact:art53` |
| `assure.acr-inputs` | Accessibility automated test results | EVI | P | **Y** | P | RA | `users.ui && a11y.tooling` | input to `assure.acr` |
| `assure.acr` | Accessibility conformance report (VPAT) | EVI | P | R | P | RA | `users.ui && (Q3 == gov \|\| jur.eu \|\| scale>=enterprise)` | `vpat:2.5rev`, `en301549:3.2.1` |
| `assure.a11y-statement` | Accessibility statement | DUR | P | R | P | RA | `users.ui && (jur.eu \|\| jur.gc \|\| scale>=enterprise)` | `eaa`, `sor2025-255` |
| `assure.ssdf-attestation` | SSDF attestation | EVI | O | R | N | RA | `jur.us_fed` (defaults not-applicable, M-26-05) | `ssdf`, `omb:m-26-05` |

Note the pattern in the `Y` entries: `attack-surface`, `scanning-index`, `control-mapping`, and `acr-inputs` are all **inputs to** an instrument, never the instrument. That is the whole compliance posture in four rows. The fifth, `sbom`, is fully automatic from a lockfile and is the flagship demo.

#### Stage 7: operate (22)

| id | Document | D | Sc | Pr | BF | Cad | Selects on | Satisfies |
|---|---|---|---|---|---|---|---|---|
| `operate.service-design-package` | Service design package (ITIL v3 term) | DUR | P | M | P | RA | `jur.gc \|\| ops.itsm` | `itil3:sdp` |
| `operate.orr` | Operational readiness review scorecard | EVI | P | **Y** | H | RE | `has_service && operated_by_others` | `itil:svt` |
| `operate.runbook-index` | Runbook index and alert coverage | DUR | P | **Y** | H | RQ | `ops.alerts` | |
| `operate.runbook` | Runbook (per scenario) | DUR | P | M | N | RQ | `ops.alerts` | `diataxis:how-to` |
| `operate.support-model` | Support model and escalation matrix | DUR | O | M | P | RS | `has_service && scale>=funded` | `itil:service-desk` |
| `operate.oncall` | On-call policy | DUR | O | M | P | RQ | `ops.oncall` | |
| `operate.service-record` | Service catalogue / CMDB entry | DUR | P | M | H | RQ | `has_service && scale>=enterprise` | `itil:scm`, `backstage` |
| `operate.bia` | Business impact analysis | DUR | P | M | N | RA | `has_service && scale>=funded` | upstream of `dr-bcp` |
| `operate.dr-bcp` | Disaster recovery and continuity | DUR | P | M | P | RA | `has_service && scale>=funded` | `iso27001:A.5.29`, `itil:continuity` |
| `operate.dr-exercise` | DR exercise and tabletop record | EVI | P | M | N | RA | `operate.dr-bcp present` | `iso27001:A.5.30` |
| `operate.backup-restore` | Backup and restore procedure | DUR | P | M | H | RQ | `data.schema \|\| has_service` | `iso27001:A.8.13` |
| `operate.capacity-plan` | Capacity plan | DUR | P | M | P | RS | `has_service && scale>=funded` | `itil:capacity` |
| `operate.hypercare` | Hypercare plan | TRA | P | M | N | RN | `scale>=enterprise \|\| jur.gc` | |
| `operate.known-errors` | Known error database | DUR | P | M | P | RM | `has_service && scale>=funded` | `itil:problem` |
| `operate.slo` | Service level objectives | DUR | P | M | P | RQ | `has_service && scale>=funded` | |
| `operate.sla` | Contractual SLA | DUR | O | M | N | RA | `scale>=enterprise && users.external` | `itil:slm` |
| `operate.observability` | Observability standard | DUR | P | M | H | RS | `has_service` | `otel` |
| `operate.incident-mgmt` | Incident management process | DUR | O | M | P | RA | `has_service && scale>=funded` | `itil:incident` |
| `operate.postmortem` | Incident post-mortem | EVI | P | M | P | RN | `has_service && scale>=funded` | `ssdf:RV.3` |
| `operate.change-enablement` | Change enablement procedure | DUR | O | M | P | RA | `has_service && (scale>=enterprise \|\| jur.gc)` | `itil:change` |
| `operate.deployment` | Release and deployment plan | DUR | P | M | H | RE | `has_service` | `itil:release`, `ssdf:PS.4` |
| `operate.data-lineage` | Data lineage (static, labelled) | DUR | P | M | P | RQ | `data.pipeline` | detect `openlineage` |

`operate.runbook-index` is `Y` and `operate.runbook` is `M`. That split is deliberate and load-bearing: an alert-to-runbook coverage table is derivable and safe; a remediation procedure executed at 03:00 by someone who did not write the system is the single highest-consequence hallucination in the catalog.

#### Stage 8: serve (17)

| id | Document | D | Sc | Pr | BF | Cad | Selects on | Satisfies |
|---|---|---|---|---|---|---|---|---|
| `serve.changelog` | Changelog | DUR | R | M | P | RE | `has_release_process` | `keepachangelog:1.1.0` |
| `serve.release-notes` | Release notes | DUR | P | M | P | RE | `users.external && has_release_process` | |
| `serve.tutorial` | Tutorial | DUR | P | M | P | RS | `users.external \|\| is_oss` | `diataxis:tutorial` |
| `serve.how-to` | How-to guides | DUR | P | M | P | RS | `users.external` | `diataxis:how-to` |
| `serve.reference` | Curated reference | DUR | P | M | H | RC | `iface.* \|\| is_oss` | `diataxis:reference` |
| `serve.explanation` | Explanation | DUR | P | M | P | RA | `users.external && scale>=funded` | `diataxis:explanation` |
| `serve.user-admin-guide` | User and admin guide | DUR | P | M | P | RS | `users.external && scale>=funded` | |
| `serve.kb` | Knowledge base articles | DUR | P | M | P | RQ | `users.external && scale>=funded` | `diataxis:how-to` |
| `serve.migration-guide` | Migration and upgrade guide | DUR | P | **Y** | H | RE | `users.external && breaking_changes` | |
| `serve.docs-site` | Developer portal config | DUR | R | M | H | RC | `docs.site_generator` | |
| `serve.training-materials` | Training and enablement | DUR | O | M | N | RA | `scale>=enterprise \|\| jur.gc` | |
| `serve.support-policy` | Deprecation and support policy | DUR | P | M | P | RA | `is_oss \|\| ships_artifact \|\| jur.eu` | `cra:annexII` |
| `serve.system-card` | System card | DUR | P | M | P | RS | `ai.present && users.external` | `aiact:annexIV` |
| `serve.ai-transparency` | AI Act Article 50 disclosure notice | DUR | P | M | P | RA | `ai.present && users.external && jur.eu` | `aiact:art50` |
| `serve.terms` | Terms of service / EULA / AUP | DUR | O | R | N | RA | `users.external` | |
| `serve.status-comms` | Status page and incident comms templates | DUR | O | M | N | RA | `has_service && users.external` | `gdpr:art34`, `cra:art14` |
| `serve.trust-pack` | Trust center and questionnaire pack | DUR | O | M | P | RQ | `users.external && Q3 == auditor` | `soc2`, `caiq` |

#### Stage 9: govern (15)

| id | Document | D | Sc | Pr | BF | Cad | Selects on | Satisfies |
|---|---|---|---|---|---|---|---|---|
| `govern.manifest` | Documentation manifest | DUR | R | **Y** | H | RQ | `always` | docdna's own output |
| `govern.traceability` | Traceability index | DUR | P | **Y** | H | RC | `verify.rtm \|\| decide.adr present` | |
| `govern.compliance-register` | Regime applicability register | DUR | P | **Y** | P | RQ | `always` | |
| `govern.raid` | RAID log | DUR | P | M | P | RM | `scale>=funded` | none (bespoke, say so) |
| `govern.raci` | Responsibility assignment | DUR | P | M | P | RS | `multi_team \|\| scale>=enterprise` | `ssdf:PO.2.1` |
| `govern.tech-debt` | Technical debt register | DUR | R | **Y** | H | RQ | `scale>=internal` | `iso25010` (category axis only) |
| `govern.ai-risks` | AI risk register | DUR | P | M | P | RQ | `ai.present` | `nist-ai-600-1` |
| `govern.ai-inventory` | AI use case inventory | DUR | O | M | H | RS | `ai.present && (jur.us_fed \|\| jur.gc \|\| scale>=enterprise)` | `omb:m-25-21`, `gc-ai-register` |
| `govern.ownership` | Ownership map | DUR | R | **Y** | H | RQ | `multi_team` | |
| `govern.contracts-index` | Contracts and SOW index | EVI | O | M | N | RA | `scale>=enterprise \|\| Q3 == gov` | |
| `govern.cost-model` | Budget and cost model | DUR | P | M | P | RQ | `scale>=funded` | |
| `govern.benefits-review` | Benefits realization review | EVI | P | M | N | RA | `scale>=enterprise` | |
| `govern.oss-policy` | OSS contribution policy and CLA/DCO | DUR | O | M | P | RA | `is_oss` | |
| `govern.export-control` | Export control classification | DUR | O | M | N | RA | `sec.crypto && ships_artifact` | `ear:742.15b` |
| `govern.records-retention` | Records retention and legal hold | DUR | O | M | N | RA | `scale>=enterprise \|\| jur.gc` | |

#### Stage 10: retire (5)

| id | Document | D | Sc | Pr | BF | Cad | Selects on | Satisfies |
|---|---|---|---|---|---|---|---|---|
| `retire.decommissioning` | Decommissioning plan | DUR | P | M | P | RA | `has_service && scale>=enterprise` | `itil` |
| `retire.data-disposition` | Data disposition record | EVI | P | M | P | RN | `data.pii && decommissioning` | `iso27001:A.8.10` |
| `retire.archive-manifest` | Archive and retention manifest | EVI | P | **Y** | H | RA | `regulated` | derived from `retention` fields |
| `retire.eol-notice` | End-of-life notice | TRA | P | M | P | RN | `users.external && retiring` | `cra:annexII` |
| `retire.closeout` | Project closeout and lessons learned | EVI | P | M | P | RN | `scale>=enterprise \|\| jur.gc` | |

### 4.5 Catalog totals

| Stage | Entries | `Y` producible | `M` manifest-only | `R` refuse |
|---|---|---|---|---|
| frame | 11 | 4 | 7 | 0 |
| decide | 6 | 3 | 3 | 0 |
| design | 13 | 5 | 7 | 1 |
| build | 19 | 12 | 7 | 0 |
| verify | 12 | 3 | 8 | 1 |
| assure | 39 | 5 | 21 | 13 |
| operate | 22 | 2 | 20 | 0 |
| serve | 17 | 1 | 15 | 1 |
| govern | 15 | 5 | 10 | 0 |
| retire | 5 | 1 | 4 | 0 |
| **Total** | **159** | **41** | **102** | **16** |

`tests/test_catalog.py` asserts these counts exactly. A PR that changes a count changes the test in the same commit; that is how the catalog stays a decision instead of a drawer.

Note that **41 entries carry a template and 118 do not.** The adversarial critique wanted 25 producible; the completeness critique wanted 28 more classes. Both are satisfied: the catalog is large because naming a document as not-applicable-with-a-reason is cheap and is the audit value, and the writing surface is small because a template is an invitation.

### 4.6 Explicitly out of scope: transient artifacts

Named so the omission is a stated decision, not an oversight. Each carries the durable artifact that absorbs its lasting content.

| Transient artifact | Absorbed by |
|---|---|
| Sprint backlog, sprint goal | `frame.roadmap`, `frame.requirements` |
| Standup notes, status reports | `govern.raid`, `decide.adr` |
| Meeting minutes, decision emails | `decide.adr` |
| Burndown and velocity charts | `frame.success-metrics` |
| Design proposals and TDDs | `decide.adr` (linked from More Information) |
| Spike reports | `decide.adr` |
| Wireframes and comps | `design.design-system`, `design.ui-spec` |
| Hypercare daily logs | `operate.known-errors`, `operate.postmortem` |
| Marketing copy variants | `serve.release-notes` |

**Rule: when the user asks for one of these, name it, state why it is not reconstructable, and offer the durable artifact.** Do not quietly generate a plausible-looking fake.

### 4.7 Three merges, stated so nothing looks dropped

- `decision-log` merges into `decide.adr-index`.
- `risk-register` merges into `govern.raid` as the R lane. The common real-world failure is keeping R and silently dropping A, I, and D.
- `tech-selection` merges into `decide.adr`. A stack choice is a decision and belongs in a numbered ADR.

---

## 5. Archetypes and the selection engine

### 5.1 Design contract

Five rules govern the engine. They exist because the failure mode of a doc-selection engine is not "missed a document"; it is "asserted a document was unnecessary without looking".

1. **Three-valued signals.** Every signal is `present`, `absent`, or `unknown`. Absence of evidence is never encoded as `false`. A grep that never ran because its gate did not fire returns `unknown`, and `unknown` never silences a document.
2. **Evidence or it did not happen.** Every `present` signal carries at least one `{path, line, match}`. A signal with no evidence is a bug and the scanner fails loudly.
3. **Exclusions are decisions, and decisions are auditable.** `not-applicable` requires a `because`, a `cite` list, and a `revisit_when` predicate.
4. **Escalation is monotonic.** Rules may raise a verdict, not lower it, unless the rule declares `force: true`. A forced downgrade is recorded with its rule id.
5. **Assumed answers are visible with their blast radius.** An unattended run still produces a manifest; every inferred answer is labelled `assumed` with the signal that produced it and a counterfactual stating what changes if it is wrong.

### 5.2 The walk

`docdna_scan.py` builds its own file index; codedna's `collect_files` is wrong for this job in three specific ways.

```python
DOT_ALLOW = {".github", ".gitlab", ".circleci", ".buildkite", ".azure", ".azuredevops",
             ".devcontainer", ".well-known", ".claude", ".cursor", ".windsurf", ".devin",
             ".vscode", ".changeset", ".config", ".vanta"}
IGNORE    = {".git", "node_modules", "dist", "build", "out", "target", "vendor", ".next",
             ".svelte-kit", "venv", ".venv", "__pycache__", "coverage", ".terraform",
             ".mypy_cache", ".pytest_cache", ".gradle", "Pods"}
DENY_READ = {".env"}   # matched by prefix; .env.example/.sample/.template are allowed
```

- **Fix 1.** Prune with `d in IGNORE or (d.startswith(".") and d not in DOT_ALLOW)`. codedna's `not d.startswith(".")` kills `.github/`, which for a doc-needs scanner holds the highest-value signals in the repo.
- **Fix 2.** The path index records **every** path. Only files a detector asks for are read. Documentation, manifest, and config extensions join the read set; `.docx` and `.pdf` are indexed and counted but never parsed, so an enterprise doc tree is visible rather than invisible.
- **Fix 3.** Honour `.gitignore` via `git ls-files --cached --others --exclude-standard` when `.git` exists, with the manual walk as fallback. **`DENY_READ` applies to both paths**, not only the git path, because a committed `.env` is common.

Git metadata is used, unlike codedna: `git rev-parse HEAD`, `git status --porcelain`, `git shortlog -sne`, `git log -1 --format=%H|%aI -- <path>`. Every git call degrades to null in a non-git directory rather than failing.

### 5.3 Signal families

Fifteen families, fixed enum, and the family name is the id namespace: `arch`, `deploy`, `iface`, `data`, `ai`, `users`, `sec`, `supply`, `ops`, `qual`, `jur`, `proc`, `docs`, `a11y`, `scale`.

Three passes, gated:

- **Pass 1 (cheap, always).** Path index, manifest parsing, git. Roughly 120 signals, no source reads. Sub-second.
- **Pass 2 (medium, gated).** Greps whose gate fired in pass 1. The AI family is gated on a manifest dependency; the interface family on `arch.service` candidates or any `deploy.*`; the data family on `data.migrations || data.orm || data.ddl`. An ungated grep that never ran reports `unknown`.
- **Pass 3 (deep, `--deep`).** Per-document `git log -1` for the staleness matrix. Skipped by default above 200 documents.

### 5.4 Signal corrections the critiques forced

The adversarial critique ran the proposed regexes and found five that misfire. All five are fixed here, and the fixes are normative.

| Signal | Old behaviour | Fix |
|---|---|---|
| `data.pii` | Lexicon hit in a schema file. Fires on a weather API's `latitude`, a request log's `ip_address`, an SMTP queue's `email`. | Requires **all three**: a lexicon hit, the column sitting on an entity the code treats as a person (table or model name in a person lexicon, or a foreign key to a users table), and confidence capped at `medium`. |
| `sec.weak_crypto` | `\b(md5\|sha1\|\bdes\b\|\brc4\b\|ECB)\b`. Matched the French article "des" three times in a four-string locale file. | Delete `\bdes\b` and `ECB`; they are unrecoverable. Require call context: `hashlib.md5(`, `crypto.createHash\(['"]md5`, `MessageDigest.getInstance\("MD5"`. Globally exclude `**/locales/**`, `**/i18n/**`, `*.po`, and all lockfiles from every security lexicon. |
| `iface.http` | `\b(app\|router)\.(get\|post)\(`. Fires on a client-side Vue router. | Requires corroboration from a server-side import in the same file (`express`, `fastify`, `hono`, `net/http`, `Flask`, `FastAPI`, `gin`) or a bind/listen call. Every runtime pattern gets a client-side fixture before shipping. |
| `ai.decides_about_people` | Derived from an LLM SDK plus a domain lexicon. Fired five times on a parser containing `candidates = [n for n in nodes if n.eligible]`. | **Deleted as a derived signal.** This is Q4 only. A lexicon hit may open the question; it may never answer it. |
| `jur.*` (all) | `users.bilingual_en_fr` derived GC from any `en` plus `fr` locale pair. A region-name constant fired both EU and GC. A GDPR library's README fired EU on prose. | **Every jurisdiction signal is demoted from verdict-setting to `hint`.** A hint may open a question; it may never set a verdict. GC additionally requires `fr-CA` (not `fr`) plus a second independent signal (a `.gc.ca` domain, GCDS components, or Protected-B vocabulary). Region enums and README prose are excluded from jurisdiction detection entirely. |

**The global rule that follows from these:** no `producible: R` entry is ever escalated to `required` or `recommended` by a signal alone. Legal instruments require an interview answer. This is enforced in `docdna_select.py`, not in prose.

### 5.5 What the scanner refuses to guess

Emitted as `state: unknown` with a reason, each mapped to an interview question: `repo.visibility`, `users.external_count`, `ops.operator_identity`, `compliance.authorizer`, `business.rto`, `business.rpo`, `docs.system_of_record`, `contract.sla_exists`, `data.lawful_basis`.

Every available proxy for these is wrong often enough to produce confidently false compliance verdicts. That is the failure mode most worth avoiding.

### 5.6 Archetypes

**Eight primaries, mutually exclusive, plus an `unknown` floor.**

| Primary | Discriminating signals | Baseline |
|---|---|---|
| `solo-utility` | `proc.authors_12mo <= 1`, no `deploy.cd`, no `sec.authn`, `proc.commits_12mo < 100` | 4 |
| `oss-library` | `users.published_package`, permissive `supply.license`, `proc.contributing`, no `iface.http` | 9 |
| `internal-service` | `deploy.cd`, `iface.http`, `sec.authn`, no `users.public_signup` | 18 |
| `commercial-saas` | `data.multi_tenant`, `users.public_signup`, `sec.payments`, `deploy.env_count >= 2` | 31 |
| `client-application` | `arch.webapp \|\| arch.mobile \|\| arch.desktop \|\| arch.extension`, `users.ui` | 16 |
| `data-platform` | `arch.data_pipeline`, `data.warehouse`, `design.data-contract`, `deploy.scheduled` | 21 |
| `embedded-device` | `arch.firmware` (Zephyr/Yocto/ESP-IDF/`*.dts`), OTA tooling, `ships_artifact` | 23 |
| `research-artifact` | notebooks with committed outputs, `CITATION.cff`, no `deploy.*`, academic manifest patterns | 12 |
| `unknown` | top score below the floor threshold | 0, interview mandatory |

**Scoring** is a weighted evidence sum, not a decision tree, so partial matches produce a runner-up and a confidence. Primary is the argmax over matched weight divided by total positive weight. **If the top two are within 15 points, emit an `archetype_counterfactual` listing the document delta**, and refuse to write any `assure`-stage document under low confidence. Under the floor threshold, the archetype is `unknown` and the interview is mandatory.

**Ten overlays, additive.** Overlays answer "what extra obligations", not "what is this thing". Modelling health, payments, or safety-critical as primaries forces a false choice and duplicates every baseline row.

| Overlay | Trigger | Adds |
|---|---|---|
| `ai-system` | `ai.inference \|\| ai.training` | model card, dataset card, eval report, AI risk register, prompt change log, provenance statement, transparency notice |
| `regulated:{gc,us-fed,eu}` | Q3 plus jurisdiction hints | control mapping, evidence indices, jurisdiction-specific `R` rows |
| `shipped-artifact` | `deploy.artifact_published \|\| arch.firmware` | SBOM, NOTICE, support-period statement, secure-update procedure, VDP |
| `public-ui` | `users.ui && Q1 in {customers, public}` | ACR inputs, accessibility statement, Diataxis set, release notes, KB |
| `operated-by-others` | Q2 in {separate-ops-team, customer-operated} | the ITIL service-transition set (11 rows) |
| `safety-critical` | `arch.safety_std` (IEC 61508/26262/DO-178C/62304 references) | safety plan, hazard analysis, ASIL/DAL allocation, tool qualification, assurance case, MC/DC evidence |
| `health` | `sec.health` | SaMD classification, 62304 lifecycle file, 14971 risk file, HIPAA SRA, BAA, FHIR conformance |
| `payments` | `sec.payments` | PCI SAQ/AoC, cardholder data flow diagram, key management, SCA evidence, KYC/AML |
| `app-store` | `arch.mobile \|\| arch.extension` | privacy nutrition labels, data safety declaration, per-permission rationale, export compliance, review notes |
| `agent-skill-package` | `arch.agent_skill` (a `SKILL.md` with valid frontmatter) | trigger contract and eval evidence, host compatibility matrix, install/uninstall procedure, non-goals as a shipped document |

**Rejected as primaries, with reasons.** Scale is a continuum and arrives as signals; making it an archetype re-creates the audience-tier mistake. Monolith versus microservices changes the depth of the Building Block View, not the membership of the set. Infra module is `oss-library` with a reference-doc shape delta, four rows different. Mobile versus web share accessibility, release notes, guides, and privacy disclosure; they differ by store paperwork, which is the `app-store` overlay.

### 5.7 The interview

**Eight questions. Zero are asked on the first run.**

The prior design gated all value behind four to seven questions. It also shipped the machinery to avoid that: signal-derived defaults, `source: assumed`, and per-answer counterfactuals. Use it. Assume, show the assumption with its blast radius, and let the user correct in one sentence.

| # | Question | Answers | Default from | Docs moved |
|---|---|---|---|---|
| Q1 | Who uses this, besides you? | `nobody` / `my-team` / `other-teams` / `customers` / `public` | `public` if published package plus permissive licence; `customers` if public signup plus multi-tenant; `my-team` if CD without public signup; else `nobody` | 14 |
| Q2 | Who runs it in production, and can they page someone? | `not-deployed` / `the-authors` / `separate-ops-team` / `customer-operated` | `the-authors` if any `deploy.cd`; else `not-deployed` | 13 |
| Q3 | Is there an external body that can audit, certify, or authorize this before it ships? | `none` / `customer-security-review` / `soc2-or-iso-auditor` / `government-authorizer` / `sector-regulator` | `government-authorizer` only on a **corroborated** GC or US-federal hint; `soc2-or-iso-auditor` if a compliance program is detected; else `none` | 19 |
| Q4 | Does it make, or materially assist, decisions about individual people? | `no` / `internal-ops-only` / `affects-money-services-employment-or-legal-status` | **always `no`.** No signal may set this. | 8 |
| Q5 | Which markets do your users sit in? | multi-select `my-org-only` / `canada` / `us` / `eu-eea` / `global` | `my-org-only` unless a corroborated jurisdiction hint fired | 11 |
| Q6 | If it were down for a day, what breaks and how fast must it be back? | `nothing` / `inconvenience-days` / `business-process-hours` / `revenue-or-safety-minutes` | `inconvenience-days` with CD and no on-call; `business-process-hours` with on-call | 5 |
| Q7 | Will anyone maintain these documents after today? | `named-owner` / `a-team` / `snapshot` | `a-team` if CODEOWNERS; `named-owner` if single author; else `snapshot` | 0, but see below |
| Q8 | Where does your documentation live? | `repo` / `repo-plus-wiki` / `mostly-elsewhere` | `repo`, **stated unconditionally in the first report** | 0, but flips `system_of_record` on every `P` and `O` row |

**Q4 defaults to `no` unconditionally.** Whether a system makes automated decisions about individuals is not detectable from token frequency, and eight documents, several regulator-facing, hang off it.

**Q7 is not cosmetic.** Under `snapshot`, output is capped to the mechanically regenerable set and the judgment-bearing set is refused with a stated reason. A document regenerable in one command is safe to leave unmaintained. A threat model is not.

**Q8 is stated in every first report whether or not it is asked**, because "I only see documentation committed to this repo" is the difference between a tool that understands a real company and one that has never seen one.

**Persistence.** Answers land in `.docdna/manifest.json` under `interview` and are read back, so re-running is non-interactive and idempotent. Editing an answer by hand and re-running is the supported way to change the selection.

### 5.8 The counterfactual dial

Every report ends with this block, computed by re-running the rule engine with one answer flipped:

```
Currently required: 19 documents.

  a separate ops team runs this        +11
  you sell to EU customers              +9
  a government buyer is in the loop    +19
  this handles special-category data    +6

Turn any of these on and I will redo the manifest. Nothing is written until you say so.
```

It costs one extra rule-engine pass per row and it converts a formless anxiety into a model the user can manipulate. It is also the artifact a lead forwards to a director, because it makes the cost of a business decision legible in units of work.

### 5.9 Verdict times state equals action

Four verdicts describe need. State describes what exists. Action is the product.

| | absent | present-fresh | present-drifted | present-stub |
|---|---|---|---|---|
| **required** | `write` | `adopt` | `refresh` | `complete` |
| **recommended** | `offer` | `adopt` | `refresh` | `complete` |
| **optional** | `note` | `adopt` | `note` | `note` |
| **not-applicable** | `skip` | `orphan` | `orphan` | `orphan` |

`orphan` is a real result: a document the repo carries that nothing in the profile justifies. That is where doc rot starts. `adopt` is the cheap win: the document is fine and just lacks lifecycle metadata.

### 5.10 Rule precedence

| Layer | Precedence |
|---|---|
| Archetype baseline | 0 |
| Signal deltas | 10 |
| Overlays | 20 |
| Interview answers | 30 |
| User overrides read back from the manifest | 40 |

Within and across layers, a rule may only raise the verdict on `not-applicable < optional < recommended < required` unless it declares `force: true`. Without this property, a poorly ordered exclusion rule silently deletes a document a regulator expects.

---

## 6. Document lifecycle frontmatter and the traceability spine

### 6.1 The schema

There is no standard here, so do not invent one. Two ratified precedents put document status in YAML frontmatter: MADR 4.0.0 (`status`, `date`, `decision-makers`, `consulted`, `informed`) and ODCS 3.1.0 (`status: proposed|draft|active|deprecated|retired`, a Linux Foundation standard). Two independent bodies converging is enough precedent. Generalize MADR's shape and add the fields a repo scanner can populate mechanically.

```yaml
---
id: assure.attack-surface
instance_id: null              # for numbered classes: adr-0014, inc-20260714-01
title: Attack surface inventory
stage: assure
durability: durable
scope: product
system_of_record: repo         # repo | external
classification: unclassified   # unclassified | protected-a | protected-b | internal | confidential

status: draft                  # draft | active | deprecated | superseded | retired | not-applicable
owner: unassigned
owner_candidate: "@platform-team (from CODEOWNERS, unconfirmed)"
reviewed_by: null
last_reviewed: 2026-07-31
review_cadence: P180D
next_review: 2027-01-27
retention: indefinite
valid_until: null              # for evidence: the date the artifact expires
supersedes: []
superseded_by: null
not_applicable_reason: null

covers:                        # FILES, never directories. Lint rejects globs.
  - src/api/routes.py
  - infra/network.tf
covers_digest: sha256:9f2a1c…  # digest of extracted declarations, not a commit sha
drift_budget: 3                # fires after N declaration changes, default 1
last_validated_commit: 639dfe7 # provenance only, never the drift test
applies_to: "v2.4.0"

satisfies: [ssdf:PW.1.1, iso27001:A.8.27]
audiences: [engineering, security]
traces_up: [req-0113]
traces_down: [tc-0442, "module:src/api/routes.py"]

derivation: derived            # derived | drafted | stub | human-authored
confidence: high
generated_by: docdna v0.1.0
generated_on: 2026-07-31
content_hash: sha256:a1b2c3…   # of the body at generation time
open_questions:
  - "Is the tenant boundary contractual or only technical?"
---
```

### 6.2 Drift, corrected

The adversarial critique modelled the prior design's drift test and found it saturates: at twenty commits a week, a directory-scoped `covers:` is stale within seven days with essentially probability one. Every document permanently red, the CI gate disabled in week two, and the single differentiator turned off first. That is fatal and the fix is structural.

Four changes, all normative:

1. **`covers:` names files, never directories.** `docdna_check.py` rejects a directory or a glob at lint time with a hard error. `covers:` must name interface-defining files: a schema, a route table, a config struct, `openapi.yaml`, a public export surface.
2. **Drift is computed over `covers_digest`**, a sha256 over the *extracted declaration names* from those files (function and class names, route paths, column names, exported symbols), not over a commit sha. A comment change, a reformat, or an added import does not fire.
3. **`drift_budget`** allows N declaration changes before firing. Default 1 for `assure` and `design`, 3 elsewhere.
4. **Drift is a warning by default.** CI gates only on an explicit `assurance_set` the user names in `.docdna/config.json`, typically three to five documents.

Four verdicts, computed independently and never conflated:

```
calendar-stale = review_cadence != none AND (today - last_reviewed) > review_cadence
drift-stale    = covers != [] AND recomputed_digest != covers_digest beyond drift_budget
expiry-stale   = valid_until != null AND today > valid_until
unverifiable   = covers == []
```

`unverifiable` is the honest state for `frame` and `govern` documents and must never be reported as a failure. Reporting a business case as drift-stale would be theater.

### 6.3 Non-Markdown documents

Roughly a dozen catalog entries point at `openapi.yaml`, `catalog-info.yaml`, `CODEOWNERS`, `.well-known/security.txt`, `sbom/*.cdx.json`, or `NOTICE`. Frontmatter has nowhere to go. **Sidecar convention: `.docdna/meta/<id>.yml`.** A catalog entry whose path is non-Markdown must have a sidecar, and the lint enforces it.

### 6.4 Supersession and retirement

- **Immutable classes** (`durability: evidence`, plus `decide.adr`): never edit an accepted file. Mint a new instance id, set `supersedes` on the new file and `superseded_by` plus `status: superseded` on the old. The old file stays. Numbers are never reused.
- **Mutable classes** (everything else `DUR`): edit in place, bump `last_reviewed` and `covers_digest`.
- **Retirement**: `status: retired` plus `retired_on`. Retired is not deleted; deletion is a records-management decision.

### 6.5 Owners are candidates, never assignments

`owner: unassigned` plus `owner_candidate: "@platform-team (from CODEOWNERS, unconfirmed)"`. **`docdna_check.py` never fails on `unassigned`.** Writing `owner: @platform-team` into a DR plan that team never agreed to own, and then failing CI until someone is named, is a social failure mode, and social failure modes get a tool banned from a team faster than technical ones. Report it as an open question addressed to a human, which is what it is.

### 6.6 The traceability spine

**Identifier scheme.** Prefixes denote node class, not stage, so a document changing stage does not break links. Repo-qualified where the spine crosses repos.

| Prefix | Node | Example |
|---|---|---|
| `bc-###` | business case | `bc-001` |
| `prd-###` | requirements spec | `prd-001` |
| `req-####` | requirement | `req-0113` |
| `adr-####` | decision | `adr-0014` |
| `rsk-###` / `thr-###` / `ctl-###` | risk / threat / control | `ctl-AC-2` |
| `epic:` / `story:` | work item | `story:gh:acme/app#412` |
| `module:` | code location | `module:acme/app@src/db/rls` |
| `tc-####` / `test:` | test case | `test:tests/test_rls.py::test_isolation` |
| `rel:` | release | `rel:v2.3.0` |
| `inc-YYYYMMDD-NN` / `pm-###` | incident / post-mortem | `pm-017` |

**Ordering, resolved.** The prior designs disagreed about whether requirement precedes epic. It does: `bc -> prd -> req -> {adr, epic -> story -> commit -> rel, tc}`. Epics and stories implement requirements; they do not produce them.

**Three spines, not one.**

```
delivery:  bc-001 -> prd-001 -> req-0113 -> adr-0014 -> module:… -> tc-0442 -> rel:v2.3.0 -> inc-… -> pm-017
assurance: rsk-004 -> ctl-AC-2 -> module:… -> evidence:sast-2026-07 -> assessment:… -> waiver-012
abuse:     thr-009 -> abuse-case-003 -> mitigation:module:… -> tc-0501
```

The assurance spine is what an SA&A package, a SOC 2 audit, and an ITSG-33 control profile actually are; without it the 39 assure entries cannot be traced at all, and traceability is the selling point. The abuse spine is what turns a threat model's STRIDE candidates into test cases; without it `assure.threat-model` and `verify.test-strategy` have no edge between them.

**Coverage is computed only from explicit annotations.** `@covers req-0113` in a test docstring, decorator, or tag. Where none exist, print `coverage: null, reason: no annotations found`. **Never a heuristic percentage.** A number derived from test-file naming will be read as measured test coverage, which is the single most misread metric in software.

**Lint rules.**

| Rule | Severity |
|---|---|
| A `traces_*` reference names an id that does not exist | error |
| Two documents claim the same `id` plus `instance_id` | error |
| A `req-` has zero `tc-` descendants | error when `regulated`, warning otherwise |
| A `thr-` has zero `tc-` descendants | warning, error when `safety-critical` |
| A `ctl-` has zero evidence descendants | warning |
| An `adr-` has zero `module:` descendants | warning |
| A `module:` exists with no `req-` ancestor | info |
| A `pm-` has no `adr-` or `tc-` descendant | warning: nothing was learned |
| A hop the skill could not fill | recorded as a tracked gap, never a silent blank |

That last row is the point. Half these edges come free from git, tests, and tags; the rest become a finite named to-do list instead of an invisible absence.

---

## 7. Evidence discipline

The failure mode is not missing documentation. It is documentation that reads authoritative and is wrong, because a template had a slot and the model filled it.

### 7.1 The rule

**Every claim block carries a citation or a GAP marker. There is no third state.** A claim block is a paragraph, a bullet, or a table row. That unit is greppable, which makes the rule enforceable rather than aspirational.

### 7.2 Four evidence classes, and no fifth

| Class | Syntax | Means |
|---|---|---|
| `code` | ``[`src/api/routes.py#register_routes`]`` or ``[`src/api/routes.py` "def register_routes"]`` | A path plus a **symbol or verbatim anchor**, at the recorded commit |
| `run` | ``[run: `python3 -m pytest --collect-only -q` -> 214 tests]`` | A named command and its captured output |
| `ref` | `[ref: references/regimes-eu.md#annex-iv, verified 2026-07-31]` | A shipped reference file carrying its own verification date |
| `human` | `[human: @hpp 2026-07-31]` | Supplied by a person in this session, attributed |

**Never a bare line number.** The adversarial critique is right: adding one import above a citation invalidates every line anchor in the file, so a document verified clean at commit A reports mass FAIL at commit A+1, and the prior design's response to FAIL was deletion. A symbol name or a verbatim anchor string survives reformatting, reordering, and insertion, and it can be relocated with a grep.

There is deliberately no class for model knowledge. "The EU AI Act Annex IV has nine areas" is a `ref`, and the reference file carries the date it was checked.

### 7.3 GAP markers

Two paired lines. The comment is for machines and renders invisibly on GitHub; the blockquote is for humans and cannot be scrolled past. The linter asserts the pair.

```markdown
<!-- GAP id=DR-004 kind=human-input sev=blocker owner=unassigned doc=operate.dr-bcp
     asks="What is the recovery time objective for the checkout service?" -->
> **GAP DR-004** (blocker): no recovery time objective is stated in code, config, or CI.
> This is a decision, not a fact, and it must be made by a person.
```

| Field | Values |
|---|---|
| `id` | `<DOC>-<NNN>`, stable, never reused even after the gap closes |
| `kind` | `human-input` \| `not-implemented` \| `unverifiable` \| `out-of-scope` \| `stale-evidence` |
| `sev` | `blocker` \| `major` \| `minor` |
| `owner` | handle or `unassigned` |
| `doc` | catalog id |
| `asks` | one quoted sentence, phrased so it can be pasted into Slack unedited |

The `kind` enum is load-bearing. `human-input` means only a person knows. `not-implemented` means the code does not do the thing, which is a product finding and not a documentation finding. `unverifiable` means the claim cannot be checked from this repo, which is where an honest document says so. `out-of-scope` requires a reason and converts a hole into a decision.

### 7.4 The verification pass, and what FAIL means

After writing and before reporting, Backfill re-reads every citation it just wrote and labels it. The stance is adversarial: assume every claim is wrong until the file proves it right.

| Label | Action |
|---|---|
| PASS | The cited symbol or anchor supports the claim as written |
| FAIL | It does not. **Delete the claim.** Do not soften it; a hedge still reads as documentation. |
| UNVERIFIABLE | The anchor resolves but does not settle the claim. Convert to a `unverifiable` GAP. |

**FAIL auto-deletes only in Backfill, only against text docdna wrote in this run.** In Check mode, against human-authored documentation, FAIL flags and a human decides. A tool that deletes a person's prose on a resolution heuristic will be uninstalled once.

### 7.5 The anti-theater rules

Four named failure modes, so they can be invoked in review.

**Paper theater.** A sentence true of any project. Test by substitution: swap the project name for a competitor's and the stack for a different one. "The system follows a layered architecture with separation of concerns" survives substitution and is therefore worthless. "Requests enter through `cmd/api/main.go`, which mounts four route groups and no middleware other than request logging" does not survive substitution and is therefore documentation.

**Checkbox headings.** A section whose body is entirely GAP markers and boilerplate is not a section; it is a request for information wearing a heading. **Rule: if a document's cited claim blocks are fewer than its GAP markers, the document is not written.** It is listed in the manifest as `status: not-started` with its blockers attached, and no file is created. An empty file that exists is worse than a missing document that is tracked, because the empty one stops anyone from noticing.

**Regime cosplay.** A DPIA for a project with no personal data. An ORR for a library with no runtime service. **Rule: every document in the manifest names the signal that selected it, with a file path.** A document that cannot name its triggering signal is not required.

**Confident fiction.** The killer, and the one specific to this skill. **No number is ever generated.** Not an RTO, an RPO, an SLA, an availability target, a capacity figure, a retention period, a support-window end date, an error budget, or a review cadence. Every one of these appears in real templates as a slot and every one is a decision a human owns. Numbers are cited or they are `human-input` GAPs. This rule is absolute and it appears twice in `SKILL.md`, once in the evidence section and once in the Backfill steps.

A fifth rule covers the manifest: **`not-applicable` requires a reason and a signal.** An unexplained exclusion is worse than a missing document, because it launders a gap into a decision.

### 7.6 Compliance guardrails and refusals

Prose guardrails lose to "just fill it in, I will review it later". The guardrail must be structural and enforced in `docdna_select.py`.

**The `producible: R` mechanism.** For the sixteen entries that are legal declarations or regulator-facing instruments, docdna:

- never emits the instrument;
- never reproduces the regulator's own section structure, because structural fidelity is precisely what makes a draft submittable;
- emits instead a differently-named evidence annex under `docs/assure/inputs/` (`pii-inventory.md`, `wcag-automated-results.md`, `control-evidence-index.md`, `attack-surface.md`);
- emits a named list of what a qualified human must supply and who must sign;
- errors at build time if a template file exists for an `R` id.

The exposure this prevents, by instrument: an ACR generated from axe-core covers roughly 30 percent of WCAG criteria and zero assistive-technology testing, and handing one to a US federal buyer is False Claims Act territory. A Canadian PIA is legally binding and goes to both OPC and TBS. An SSP inside an SA&A package asserts control implementation and is signed by a departmental authorizer; drafting "AC-2 implemented" because a grep found an IAM role is a false control assertion in an authorization package. An AI Act Annex IV file is retained ten years and inaccuracy is itself an infringement. An inadequate DPIA breaches Article 35(7) directly and, worse, stops the organization doing a real one.

**Specifically cut from v1.0: SSP drafting.** In a Government of Canada context an AI-drafted System Security Plan submitted into a departmental SA&A process is worse than no SSP: the assessor rejects it, the delivery lead's credibility is spent, and remediation is starting over with a human. `assure.saa-inputs` ships the evidence index and the control-mapping register with explicit `unknown` rows. **The unknown rows are the deliverable.**

### 7.7 The reconstruction banner

Every generated document carries this immediately under the frontmatter, plus per-section HIGH/MEDIUM/LOW confidence labels where a section rests on inference:

```markdown
> Backfilled by docdna v0.1.0 from repository evidence at commit 639dfe7 on 2026-07-31.
> Claims are cited to files and symbols. Unknowns are tracked as GAP markers, not filled in.
> This is derived, not authoritative. Schedule a human review before relying on it.
```

### 7.8 Sensitivity

Every catalog entry carries `sensitivity: public | internal | restricted`. A threat model, an access-control inventory, and a DR plan are sensitive artifacts. **docdna refuses to write an `internal` or higher document into a repo whose visibility is public or unknown without explicit confirmation.** Cheap, and it is the kind of thing that gets noticed the first time it goes wrong.

### 7.9 Reconstructed ADRs

ADRs are immutable, so a fabricated rationale is permanently in the record and can only be superseded, never corrected. That is the one document class where mistakes cannot be edited away, and it is the one being reconstructed from inference.

Rules, all normative:

- Reconstructed decisions are minted in a **distinct id space**: `adr-draft-0001`, never renumbered into the accepted sequence without an explicit human accept step.
- Frontmatter carries `retro: true` and `derivation: derived`. Status is `accepted`, not `proposed`: the decision was made, shipped, and is running, and `proposed` on a live decision either invites re-litigation or gets mistaken for a contemporaneous record.
- The **Considered Options section is absent**, not filled with "unknown". A GAP marker sits in its place.
- A `retro: true` ADR with a populated Considered Options section and no `human:` citation is a **confident fiction** lint error.
- Instance ids are date-prefixed (`adr-draft-20260731-01`) to survive concurrent branches.

---

## 8. Repo layout and progressive disclosure

The binding constraint is the Agent Skills spec: body under roughly 5000 tokens, keep under 500 lines. A catalog of 159 documents cannot live in `SKILL.md` and must not try.

**Four tiers, and the second one is the trick.**

| Tier | Loaded | Contains |
|---|---|---|
| 1. `SKILL.md` | Always, on activation | Modes, the procedure, evidence rules, GAP syntax, script invocations, refusals. Target 300 lines. |
| 2. `catalog/*.json` | Once, during Survey | The machine index of every document, signal, rule, and regime. One file read replaces 150 markdown reads. |
| 3. `references/*.md` | On demand, by name | The prose behind a decision. |
| 4. `templates/*.md` | Only when selected | One skeleton per producible entry, loaded only if the manifest chose it. |

The catalog is what keeps Survey cheap. The agent reads `documents.json` once, evaluates predicates against scanner signal ids, and produces the manifest without opening a template. A solo CLI with four selected documents never loads the other 155.

```
docdna/
  README.md                        strapline, handover pitch, 60-second sample output
  LICENSE  CODE_OF_CONDUCT.md  CONTRIBUTING.md  CHANGELOG.md  .gitignore
  install.sh                       cp -R of skill/, one positional argument
  .github/workflows/ci.yml         py_compile, unittest, shellcheck, catalog closure, reference aging
  docs/
    AGENT_SUPPORT.md               install table, wiring table, correct CLAUDE.md facts
    CATALOG-MAINTENANCE.md         named owner, cadence, the reference aging job
  skill/
    SKILL.md
    catalog/
      SCHEMA.md                    the ONE normative schema. Prose docs reference it.
      documents.json               159 entries
      signals.json                 signal id registry, families, detection rules
      rules.json                   ~140 rules
      archetypes.json              8 primaries + 10 overlays + the unknown floor
      interview.json               8 questions, defaults, counterfactual text
      regimes.json                 6 regimes at v1.0, each with a verified date
    references/
      selection.md  evidence.md  lifecycle.md  traceability.md  antipatterns.md
      method-architecture.md  method-quality.md  method-security.md
      method-operations.md  method-product.md  method-data-ai.md  method-agent.md
      regime-facts/                dated, small, only facts that gate a decision
        eu.md  us.md  canada.md  standards.md  accessibility.md  ai.md
      RESEARCH.md                  verification log and uncertainty register
    templates/
      _frontmatter.md  _gap.md  _banner.md  _document-control.md
      <41 flat files, one per producible entry, named <stage>-<slug>.md>
    scripts/
      docdna_scan.py  docdna_select.py  docdna_check.py  docdna_wire.py
  tests/
    fixtures/  solo_cli/  gc_saas/  ml_service/  documented_repo/
               client_spa/  firmware/  agent_skill/  docdna_itself/
    test_scan.py  test_select.py  test_check.py  test_wire.py
    test_catalog.py  test_docs.py  test_falsepositive.py
```

**Templates are flat, not nested.** `templates/assure-attack-surface.md`, not `templates/assure/attack-surface.md`. This sidesteps the one-level-deep guidance in the spec entirely rather than arguing about whether it applies to filesystem depth or to reference chains.

**`references/` splits into evergreen method and dated regime facts.** `method-*.md` carries no verification date and does not age. `regime-facts/*.md` carries `verified: YYYY-MM-DD`, and there are **six of them, not fifteen**, because six is what a single maintainer will actually re-verify. The aging lint reports "as of <date>, confirm before relying" as **info, never as a failure**; a skill that puts itself into permanent red on day 181 has taught its user to ignore its own output.

**`docs/CATALOG-MAINTENANCE.md` is the credibility keystone.** Named owner, quarterly cadence, a `verified:` field on every regime file, and a CI job that reports aging references in the build log. If the tool's own regime data rots silently, everything it emits is wrong with confidence, which is the exact failure mode it exists to prevent.

---

## 9. Scripts

Four, all stdlib-only, all matching codedna's Python house style exactly: no f-strings, no type hints, no function docstrings, one one-line module docstring, `%` formatting, snake_case, SCREAMING_SNAKE constants, `main(argv=None)`, optional `--json` producing `json.dumps(..., indent=2, sort_keys=True)`, text output using the `"  %-9s: %s"` aligned label column.

**JSON everywhere, never YAML.** stdlib has no `yaml` module, and the prior design's hand-rolled restricted-subset parser breaks on the first user who adds a comment or an anchor to their own canonical manifest. `.docdna/manifest.json` is canonical and machine-written. Document **frontmatter** is YAML because that is what MADR and every editor expect, and the parser for it is deliberately restricted: flat `key: value`, quoted strings, simple `- item` lists, one nesting level. **Frontmatter the parser cannot read is rejected with an error, never guessed at.**

| Script | CLI | Role |
|---|---|---|
| `docdna_scan.py` | `[repo] [--json] [--family F ...] [--deep] [--max-evidence N]` | Signals, doc inventory, drift candidates. Decides nothing. |
| `docdna_select.py` | `[repo] [--json] [--answer k=v ...] [--unattended]` | Catalog plus rules to `.docdna/manifest.json` and `DOCDNA.md`. Pure function of its inputs. |
| `docdna_check.py` | `[repo] [--json] [--fail-on {blocker,major,minor,never}] [--only {drift,lint,gaps,spine,tripwires}]` | The gate. Subsumes lint, trace, and gap rollup because they share one frontmatter walk. |
| `docdna_wire.py` | `[repo] [--agent T ...] [--all] [--json]` | Shared with codedna, marker-parameterized. |

Only `docdna_scan.py` is required by the Survey happy path. `SKILL.md` says so, so a host without Bash degrades to a manual Survey exactly as codedna degrades on its wire step.

### 9.1 `docdna_scan.py` output contract

```json
{
  "schema": 1,
  "tool": "docdna_scan",
  "version": "0.1.0",
  "generated": "2026-07-31T18:04:11Z",
  "root": "/Users/hprincivil/Projects/example",
  "root_identity": {"device": 16777234, "inode": 4815162342},
  "commit": "639dfe7c1a2b3d4e5f60718293a4b5c6d7e8f901",
  "dirty": false,
  "scan": {
    "files_total": 1842, "files_read": 1601, "files_skipped_large": 3,
    "files_denied": 1, "files_capped": 0, "read_errors": 1,
    "dirs_pruned": [".git", "node_modules", "dist"],
    "max_file_bytes": 1000000, "truncated": false
  },
  "signals": [
    {
      "id": "data.pii", "family": "data", "label": "personal data on a person entity",
      "state": "present", "confidence": "medium", "hits": 7,
      "detail": {"distinct": ["email", "date_of_birth"], "entities": ["User", "Contact"]},
      "evidence": [
        {"path": "src/models/user.py", "line": 18, "symbol": "User.email",
         "text": "email = Column(String(255), unique=True)"}
      ],
      "evidence_truncated": true
    },
    {
      "id": "jur.gc", "family": "jur", "label": "Government of Canada nexus",
      "state": "hint", "confidence": "low", "hits": 2,
      "evidence": [{"path": "locales/fr-CA/common.json", "line": 1, "text": "{"}],
      "note": "hint only; may open a question, may never set a verdict"
    }
  ],
  "inventory": {
    "docs": [
      {"path": "docs/adr/0001-use-postgres.md", "kind": "adr", "kind_confidence": "high",
       "bytes": 2140, "frontmatter_present": true,
       "frontmatter": {"status": "accepted", "date": "2025-04-02"},
       "last_commit_sha": "abc1234", "last_commit_date": "2025-04-02T11:03:00Z",
       "days_since_commit": 485, "links_out": 4, "links_broken": 1}
    ],
    "opaque": [{"path": "docs/Runbook.docx", "bytes": 41022, "parsed": false}],
    "generators": ["mkdocs.yml"],
    "counts": {"total": 34, "opaque": 3, "with_frontmatter": 2,
               "stale_over_365d": 19, "broken_links": 6}
  },
  "drift": [
    {"doc": "README.md", "line": 34, "kind": "command-not-found",
     "claim": "npm run dev",
     "checked_against": "package.json:scripts",
     "detail": "no `dev` script; scripts are build, test, start",
     "doc_last_commit": "2025-05-02", "code_last_commit": "2026-07-11",
     "confidence": "high"},
    {"doc": "docs/api.md", "kind": "count-mismatch",
     "claim": "11 endpoints", "checked_against": "src/urls.py",
     "detail": "23 routes registered", "confidence": "medium"}
  ],
  "ownership": {
    "codeowners": true, "codeowners_path": ".github/CODEOWNERS", "rules": 12,
    "top_authors": [{"name": "Hanns Peter", "commits": 214, "last": "2026-07-13"}],
    "single_author_paths": [{"path": "infra/", "authors": 1}]
  },
  "unknown": [
    {"family": "jur", "reason": "no corroborated market, hosting-region, or buyer signal"},
    {"family": "ops", "reason": "no deploy configuration; cannot determine who operates this"}
  ]
}
```

`root_identity` binds the scan to the device and inode opened for that invocation. The selector and
checker reject an imported scan when those values do not match the repository they have opened. The
values are local filesystem identity, not portable metadata: moving or copying a repository requires a
fresh scan.

Rules that are part of the contract: `evidence` is capped at `--max-evidence` (default 5) with `evidence_truncated` set; `hits` is always the full count; `text` is truncated to 160 characters and passed through a secret-shaped redactor. **The redactor is not a safety claim.** `text` is omitted entirely for any file matched by a secret-bearing path rule, and the docs say "review before sharing", never "safe to paste".

**`state` has four values, not three:** `present`, `absent`, `unknown`, `hint`. `hint` is the demoted jurisdiction tier and it is a distinct state so that no rule can accidentally consume it as `present`.

**`drift[]` is computed with zero adoption**, from documents docdna has never touched. Four checks at v0.1: command strings against `package.json` scripts / `Makefile` targets / CI steps / `pyproject` entry points; file and directory paths mentioned in docs, for existence; endpoint counts against detected routes; doc last-commit versus code last-commit for the code it names. None of these needs frontmatter, a manifest, or an interview.

### 9.2 `docdna_select.py`

Reads the scan JSON plus the five catalog files, applies precedence, writes `.docdna/manifest.json` and regenerates `DOCDNA.md`. Pure function of its inputs, so it is trivially testable against golden manifests.

Hard errors, not warnings: a template exists for a `producible: R` id; a rule references a document id absent from the catalog; a `cite` names an unregistered signal; a signal in state `hint` appears in a rule that sets a verdict; an archetype baseline references a missing document id.

Manifest shape, abbreviated:

```json
{
  "schema": 1, "generated_by": "docdna 0.1.0", "generated_at": "2026-07-31",
  "repo_head": "639dfe7",
  "archetype": {"primary": "oss-library", "score": 0.71,
                "runner_up": {"id": "solo-utility", "score": 0.63},
                "confidence": "medium", "overlays": [],
                "counterfactual": {"solo-utility": {"added": [], "removed": ["assure.sbom"]}}},
  "interview": {"q1_users": {"value": "public", "source": "assumed", "from": "users.published_package"}},
  "documents": [
    {"id": "assure.vdp", "verdict": "required", "state": "absent", "action": "write",
     "durability": "durable", "scope": "org", "system_of_record": "ask",
     "producible": "M", "path": "SECURITY.md",
     "because": ["Published artifact with no private disclosure route."],
     "cite": ["users.published_package", "sec.security_md=absent"],
     "satisfies": ["ssdf:RV.1.3", "iso29147"],
     "owner": "unassigned", "owner_candidate": "@hannsxpeter",
     "defers_to": "repo-ready", "write_status": "pending"}
  ],
  "excluded": [
    {"id": "assure.impact-screening", "rule": "R-IMPACT-NONE",
     "because": "No personal data on a person entity, no authentication, no database.",
     "cite": ["data.pii=0", "sec.authn=absent"],
     "revisit_when": {"any": [{"signal": "data.pii", "gte": 1}, {"signal": "sec.authn", "is": true}]}}
  ],
  "assumptions": [
    {"answer": "q2_operator", "assumed": "not-deployed",
     "counterfactual": "If a separate ops team runs this, 11 documents become required."}
  ],
  "drift": [ … from the scan … ],
  "spine": [{"from": "req", "to": "tc", "method": "annotation", "coverage": null,
             "reason": "no @covers annotations found"}]
}
```

**`excluded[]` lives in the JSON only.** `DOCDNA.md` renders a one-line count plus only the exclusions whose `revisit_when` is within one signal of firing. That is the actionable subset. A 127-row annotated shame list in the human view is the theater the skill exists to prevent.

**`write_status`** is `pending | in-progress | written | verified | failed`, updated after each document, and it is what makes an interrupted Backfill resumable rather than restartable.

### 9.3 `docdna_check.py`

Six passes over one frontmatter walk plus one scan:

1. **Drift**, including the zero-adoption checks, plus `covers_digest` recomputation for adopted documents.
2. **Lint**: frontmatter keys, `status` enum, `covers` containing no directory, sidecar presence for non-Markdown, citation coverage per claim block, GAP well-formedness, relative link resolution, `ref:` verification-date age (info only).
3. **Gaps**: rollup by severity, owner, and document; regenerates the `## Open gaps` block in `DOCDNA.md` between markers.
4. **Spine**: builds the three graphs, applies the lint table, reports coverage from annotations only.
5. **Tripwires**: re-evaluates every `revisit_when` in `excluded[]` and reports the ones now firing. **This is the headline output**, and it prints first when any tripwire fires.
6. **Orphans**: documents present that nothing in the profile justifies.

Exit codes: 0 clean, 1 a gated finding under `--fail-on`. The gate reads `assurance_set` from `.docdna/config.json`; with no `assurance_set`, drift is a warning and only lint errors gate.

### 9.4 `docdna_wire.py`

codedna's mechanics unchanged: first-occurrence marker `find` with a `start < end` guard, position preserved on replace, whitespace normalized to one blank line each side, `AGENTS.md` created unconditionally, other plain targets updated only when they exist, `cursor` on `.cursor/rules`, `cascade` preferring `.windsurf/rules` only when `.devin/rules` is absent. Markers and rule basenames threaded through, so codedna and docdna blocks coexist.

Block body:

```markdown
<!-- docdna:start -->
## Project documentation

The documentation set for this repo is indexed in [DOCDNA.md](DOCDNA.md): which documents exist,
who owns them, when they were last verified against the code, and what is deliberately not applicable.
Agent-readable index at [llms.txt](llms.txt). Before answering questions about how this system works,
prefer a document listed there over inference. If a document contradicts the code, the code is correct
and the document is stale; say so.
<!-- docdna:end -->
```

The last sentence is not decoration. A doc-pointer block that does not state precedence makes stale documentation authoritative, which is worse than no block at all.

**Claude Code reads `CLAUDE.md`, not `AGENTS.md`.** Multiple widely-cited blogs say otherwise and are wrong; Anthropic's documentation states it plainly. `docs/AGENT_SUPPORT.md` must get this right, because being wrong about agent context files in a skill that generates agent context files is unrecoverable. Wire `CLAUDE.md` explicitly. Offer the `@AGENTS.md` import as the interop path. Do not recommend the symlink; it needs Administrator or Developer Mode on Windows.

---

## 10. First-run experience

The cost profile is fine: stdlib Python over a path index with gated greps is under 5 seconds on 30k LOC. The failure in the prior design was never speed; it was **what gets shown first**. It led with absence, which is abstract, arguable, and easy to dismiss. The thing that lands in 60 seconds is **contradiction**: a document you already have that the code proves is wrong. That is concrete, undeniable, slightly embarrassing, and it is why someone installs the tool.

**The minimum viable first output, universal shape:** one screen, drift first, gaps second, exclusions in one line, assumption with blast radius, next actions at the bottom. Zero questions.

### 10.1 A 400-line personal CLI

```
docdna  solo-utility  ·  412 lines Python  ·  1 author  ·  MIT  ·  3 tags  ·  nothing deployed

Documentation  2 of 4        Drift  1 of your 2 documents contradicts the code

WRONG NOW
  README.md            says `pip install -e .`; pyproject has no build-system table,
                       so that command fails on a clean machine

MISSING AND LOAD-BEARING
  SECURITY.md          you publish releases; there is no private reporting route
  CHANGELOG.md         3 tags, no release notes

NOT APPLICABLE  155 documents. Nothing is deployed, no data, no users but you.
                Full ledger: .docdna/manifest.json

ASSUMED         nobody else operates this and no regulator sees it.
                If a government buyer is in the loop, 19 documents become required.

NEXT            write both  ·  show the full manifest  ·  check every doc against the code
```

Under 20 lines against 412 lines of Python. The prior design produced roughly 1,400 lines here, because it rendered 149 exclusion rows with reasons, citations, and tripwires into the human view. That output volume is inversely correlated with the project's need, and it violates two of the skill's own anti-theater rules.

### 10.2 A 30k-LOC internal Django service

This is the sweet spot. Scan 3 to 8 seconds, archetype `internal-service` at 0.75 with a clear win, no question needed.

```
docdna  internal-service  ·  24k LOC Python/Django  ·  3 contributors  ·  GH Actions to k8s

Documentation  7 of 19       Drift  3 of your 7 documents contradict the code

WRONG NOW
  README.md            says `python manage.py runserver`;
                       Procfile and Dockerfile both run gunicorn
  docs/setup.md        last touched 2024-03-11; requirements.txt changed 47 times since
  docs/api.md          documents 11 endpoints; urls.py registers 23

MISSING AND LOAD-BEARING
  runbook coverage     12 alerts in ops/alerts.yml, 0 with a documented response
  on-call escalation   .pagerduty.yml exists; no escalation path written down
  decision records     0 ADRs; git log shows 3 framework swaps

NOT APPLICABLE  140 documents. Nothing ships to the EU, no AI, no external customers,
                no government buyer. Full ledger: .docdna/manifest.json

ASSUMED         the authors operate this. If a separate ops team does, 11 more
                documents become required (ORR, support model, escalation, on-call,
                DR/BCP, backup-restore, capacity, hypercare, KEDB, CMDB, decommissioning).

NOTE            I only see documentation committed to this repo. If your docs live in
                Confluence or Notion, say so and I will mark those rows present-elsewhere
                rather than missing.

NEXT            write the 6 derivable documents (about 8 minutes)  ·  full manifest  ·  deep check
```

That NOTE line is unconditional and it is the difference between a tool that understands a real company and one that has never seen one.

### 10.3 A regulated multi-service GC system with AI

This is the case where the prior design was dangerous. It would have selected 60 to 85 documents and offered to draft an SSP. **What this user wants is four things, in ten minutes, not seventy documents in four hours.**

```
docdna  internal-service ×4 units  ·  overlays: ai-system, public-ui  ·  jurisdiction: UNRESOLVED

I found Government-of-Canada signals but will not act on them without you.
  locales/fr-CA/ and locales/en-CA/     bilingual resource pairs
  src/ui/ imports @cdssnc/gcds-components
  infra/main.tf pins region "ca-central-1"
Q3 (is there an external authorizer?) and Q5 (which markets?) are unanswered.
Answering "government-authorizer" adds 19 documents and changes 7 more from
recommended to required. I have assumed "none".

REGIME APPLICABILITY (what fired, and where)
  EU AI Act Art. 50    ai/chat.py calls anthropic.messages.create; no c2pa or synthid
                       anywhere; user-facing output at src/ui/Chat.tsx
  CRA                  not in scope: no shipped artifact, no firmware, SaaS only
  GDPR Art. 35         not screened: Q4 unanswered, and no signal may answer it

CONTROL EVIDENCE (the unknowns are the deliverable)
  93 ITSG-33 controls in the Protected-B profile
   31 have an implementing artifact in this repo (CI step, IaC setting, policy file)
    9 are inherited from the cloud provider and need a CRM entry
   53 unknown          docs/assure/inputs/control-evidence-index.md

OPERATIONAL READINESS (mechanically checked, 17 domains)
   9 met · 5 partial · 3 absent      docs/assure/inputs/orr-scorecard.md
   absent: verified restore test, capacity plan, decommissioning plan

MUST BE SIGNED BY A HUMAN (docdna will not draft these)
  System Security Plan · Security Assessment Report · POA&M · Statement of Authorization
  PIA (submitted to OPC and TBS) · Algorithmic Impact Assessment (published, bilingual)
  Accessibility Conformance Report against EN 301 549 V3.2.1

NEXT            answer Q3 and Q5  ·  full manifest  ·  write the 3 evidence indices
```

Produce those four in ten minutes and the delivery lead becomes an evangelist. Produce 70 drafted documents and they never run it twice.

### 10.4 Backfill, bounded

Backfill never runs unbounded. A 38-document run costs roughly 1.1 million tokens and nine context windows, and the failure is not that the user stops; it is that compaction mid-run drops the manifest and the run degrades into exactly the confident fiction the skill exists to prevent.

Normative:

- **Default target is the derivable ten.** Everything judgment-bearing is opt-in, named explicitly.
- **Hard cap of 5 documents per invocation** unless `--all` is passed, and `--all` prints an estimate and waits.
- **Estimate first:** "6 documents, roughly 8 minutes." Never start without one.
- **Per-document subagent fan-out**, so each document gets a clean context with the manifest as the shared contract.
- **`write_status` written to the manifest after every document**, so an interrupt resumes.
- **`--only <id>` and `--branch`.** `--branch` is opt-in, not refused: one branch, one commit per document, and a PR body that is the manifest diff is the version a lead can actually review. Dumping 20 files into a dirty working tree is the scary version.

### 10.5 One number, tracked

Every skill in this user's ecosystem produces a score. docdna prints one headline metric with a delta on re-run:

```
Documentation coverage  7/19 (was 4/19 on 2026-05-02)
```

People do not re-run tools that do not show progress. Coverage is `present-fresh` over `required plus recommended`, computed, never estimated.

---

## 11. Non-goals and explicit refusals

Stated in `SKILL.md` under "What this does not do", because a skill that refuses nothing will be asked for everything.

1. **Does not write, fix, or change code.** It will tell you the code contradicts the document; it will not reconcile them by editing the code.
2. **Does not invent numbers.** No RTO, RPO, SLA, SLO, capacity figure, retention period, support-window end date, error budget, or review cadence is ever generated. This is the most important refusal in the list and it is stated twice.
3. **Does not certify, attest, or sign.** No ATO, CE marking, declaration of conformity, SSDF attestation, or completed VPAT. It produces the inputs an assessor needs and names who must sign. The signature line stays empty.
4. **Does not draft a System Security Plan, a PIA, a DPIA, an AIA, a FRIA, an ACR, or an AI Act Annex IV file.** Sixteen `producible: R` entries, enforced in code.
5. **Does not give legal advice, and does not assert that a regime applies.** It reports the signal, names the regime it might trigger, cites its own dated reference file, and says to confirm with counsel.
6. **Does not generate an SBOM.** Real dependency resolution is not a stdlib job. It detects the ecosystem, emits the exact `syft` or `cdxgen` command, and records that command's output as `run` evidence. A hand-written dependency list is a lie with a filename.
7. **Does not generate OpenLineage.** Lineage is a property of execution, not of source. It detects whether an integration exists and reports it. Any static lineage document is labelled "derived from static analysis, not runtime-verified".
8. **Does not run tests, scanners, the application, or anything on the network.** Read-only, plus the documents it writes and the instruction files it wires.
9. **Does not write a runbook procedure or a completed access-control matrix.** Inventory only: an alert list with "no documented remediation", a route-to-guard table with explicit `unknown` cells. A hallucinated remediation executed at 03:00 causes an outage.
10. **Does not fabricate ADR rationale.** Reconstructed decisions live in a separate id space with the Considered Options section absent.
11. **Does not maintain the documentation.** It backfills and it lints. It does not auto-commit, run on a schedule, or overwrite a document a human has edited since generation.
12. **Does not build a documentation site or pick a generator.** Plain Markdown in `docs/`. A generator config only when the repo already reveals one. Material for MkDocs reaches end of life 2026-11-05 and is never a default.
13. **Does not do project management.** No backlog, no estimates, no sprint plan, and no RACI beyond what CODEOWNERS and git history support.
14. **Does not translate.** It detects the Official Languages obligation and flags it with an owner. Machine-translating a GC accessibility statement would be worse than leaving it undone.
15. **Does not fingerprint prose style.** That is codedna's neighbourhood and it is not a documentation problem.
16. **Does not emit a folder named `rfc/`.** "RFC" means the ITIL Request for Change in any ITSM-adjacent project, and every GC system has an ITSM footprint. The debate artifact is a **design proposal**. When a repo already has `rfc/` and shows ITSM vocabulary, Check reports the collision as a naming finding.
17. **Does not write a document with zero cited claims.** A file that is entirely GAP markers is a request for information, not documentation. It is listed as `status: not-started` with its blockers, and no file is created.
18. **Does not write an `internal` or higher document into a public or unknown-visibility repo** without explicit confirmation.

---

## 12. Build order

### v0.1: the drift detector with a small manifest

The smallest thing that is loved, and it has almost no hallucination surface.

- `docdna_scan.py` complete: the walk with all three fixes, the fifteen signal families with the five corrected patterns, the doc inventory including opaque formats, and the four zero-adoption drift checks.
- `catalog/documents.json` with **the 41 producible entries only**, plus the 20 highest-value manifest-only entries. 61 rows, not 159.
- `catalog/signals.json`, `rules.json`, `archetypes.json` (8 primaries, 5 overlays: `ai-system`, `shipped-artifact`, `public-ui`, `operated-by-others`, `agent-skill-package`), `interview.json` (8 questions, none asked).
- `docdna_select.py`: manifest JSON canonical, `DOCDNA.md` as the one-screen generated view, `excluded[]` rolled up to one line, assumptions with counterfactuals, the counterfactual dial.
- **Survey mode only.** No Backfill, no Check, no wiring, no templates, no regime files.
- Tests: `test_scan.py`, `test_select.py`, `test_catalog.py`, `test_falsepositive.py` (the five corrected patterns against a client SPA, a French locale bundle, a weather API schema, a GDPR library README, and a region-name constant), plus fixtures `solo_cli`, `internal_service`, `client_spa`, `documented_repo`.

Ship the 60-second output. Nothing else.

### v0.2: Check, tripwires, and the derivable ten

- `docdna_check.py`: all six passes, with the corrected drift computation (`covers` files only, `covers_digest`, `drift_budget`, warn by default, `assurance_set` gates).
- Frontmatter schema plus `_frontmatter.md`, `_gap.md`, `_banner.md`, `_document-control.md`, and the sidecar convention.
- **Backfill limited to the derivable ten**, bounded at 5 per invocation, resumable via `write_status`, with `--only` and `--branch`.
- `revisit_when` tripwires promoted to Check's first output. This is the feature to lead the v0.2 announcement with.
- `docdna_wire.py`, shared with codedna 1.0.3.
- `llms.txt` emission as the agent-readable doc index.
- Fixtures: `gc_saas`, `ml_service`, `firmware`, `agent_skill`, `docdna_itself` with a pinned golden manifest.

### v1.0: the full catalog, regimes, and the spine

- Catalog to 159 entries with the `producible` split enforced in code.
- Six `regime-facts/*.md` with `verified` dates plus the CI aging report, and `docs/CATALOG-MAINTENANCE.md` with a named owner and a quarterly cadence.
- All ten overlays, including `regulated`, `safety-critical`, `health`, `payments`, `app-store`.
- The three spines and `docdna_check.py --only spine`.
- The remaining 31 templates.
- `scope` and `system_of_record` inheritance, `.docdna/system.yml` for cross-repo assembly, repo-qualified spine ids.
- Delegation detection via artifact shape plus a user-editable `.docdna/integrations.json`. **A missed integration is a visible manifest row ("expected harden-ready output not found at configured path"), never a silent fallback to generating a substitute.**
- Run `skills-ref validate` in CI, and run a trigger eval against the twelve competing installed descriptions before tagging.

### Deferred past v1.0, deliberately

Audience rendering and section-level zoom maps. Multi-repo system assembly beyond the `system.yml` pointer. The 28 P2 document classes the completeness critique listed (they enter the catalog as manifest-only rows or stay out). Any generator config beyond detection.

---

## 13. Open questions for the user

These genuinely need a human answer and the implementer should not guess.

1. **Confirm the name.** `docdna` wins on family lift and loses on search discovery: `docsdna.ai`, `docdna.cloud`, and a live `DOCUMENT DNA` trademark all occupy the semantic neighborhood, and none of them do what this does. The alternative with the cleanest namespace is `docdebt`, which names the buyer's emotional state and has zero GitHub repos, zero npm, zero PyPI, and no trademark, but no family lift. Family or search: pick one.
2. **Confirm the headline job.** This spec makes **handover** the pitch and compliance the depth. That inverts the original framing, which led with regulated GC work. Handover is universal, self-serving, and buyer-autonomous; audit prep is rare and coerced. If your actual near-term need is GC delivery work, say so and the README leads differently, though the machinery does not change.
3. **Who owns catalog maintenance, and at what cadence?** Six regime files with dated regulatory facts is a standing commitment. Quarterly is the proposal. If the honest answer is "nobody", cut `regime-facts/` to three (EU, Canada, standards) and drop the jurisdiction overlays to hints-only permanently.
4. **Two Canadian claims must be re-verified before they ship as assertions**, and neither could be confirmed from automated fetch: the data-classification anchor (ITSG-33 Annex 1 plus the TBS Directive on Security Management), and the AIA level-to-requirement matrix (read Appendix C of the Directive directly; the TBS pages bot-block). Until confirmed, both stay out of `regime-facts/canada.md`.
5. **Does DoD-specific SSDF attestation survive OMB M-26-05?** Confidence is low. Check DFARS and the SWFT program separately before telling a defense-adjacent user they are clear. `assure.ssdf-attestation` currently defaults to not-applicable on that basis.
6. **Do you want `--branch` on by default for Backfill?** This spec makes it opt-in. Opt-out is defensible and safer for a 5-document run.
7. **Should codedna 1.0.3 ship before or with docdna 0.1?** Before is cleaner: the description narrowing and the `replace_block` parameterization are independently correct and reduce trigger collision the day docdna lands.

---

## 14. Rejected critiques

Each of these landed somewhere. These are the parts that did not, with reasons.

**"Cut the catalog to roughly 25 producible entries" (adversarial, finding 6).** Half accepted, half rejected. Accepted: the writing surface must be small, and it is, at 41 templates. Rejected: cutting the **catalog** to 25 throws away the audit value. Naming a document as not-applicable with a reason and a tripwire costs one JSON row and is the single most defensible output for a regulated buyer, because it is the difference between "we forgot" and "we decided". The 159-entry catalog with 118 non-writing rows is not a generator; it is a ledger. The critique conflated catalog size with generation surface, and the `producible` field separates them.

**"The `DOCDNA.md` shame list is inherent to a large catalog" (adversarial, finding 21).** Rejected as stated. It was a rendering choice, not a consequence. `excluded[]` lives in JSON; the human view shows a count plus the near-firing subset. The critique's own fix is the one adopted, but the framing that a large catalog forces a large document does not hold.

**"The ADR reconstruction problem is structurally unfixable" (adversarial, finding 16).** Rejected. It is fixable with three moves the completeness critique supplied: a separate `adr-draft-` id space that never merges into the accepted sequence without a human step, `retro: true` with `status: accepted` (not `proposed`, which misrepresents a live decision), and the Considered Options section **absent** rather than populated. Immutability is only a trap if the fabricated content enters the immutable sequence, and it does not.

**"Templates two levels deep violate the Agent Skills spec" (adversarial, finding 24).** Rejected as a spec reading; the "one level deep" guidance is about reference chains from `SKILL.md`, not filesystem depth. Adopted anyway, because flat template names sidestep the argument at zero cost.

**"Ship a `test_shared_core.py` with a pinned sha256 across two repos" (architecture design, adopted by neither critique).** Rejected. It creates an ordering deadlock where no sequence leaves both CIs green during a change, it fails a repo that did nothing wrong, and it forces every per-skill tweak into both repos, which is how you get an accidental monorepo after arguing against one. The thing being protected is a fifteen-row table of agent instruction paths. Move the table to `wire_targets.json`, copy the script, and write one line in each `CONTRIBUTING.md`.

**"Rename to `docdebt`" (product, section 2).** Rejected, and it is the closest call in this document. `docdebt` has the cleaner namespace and the better standalone legibility. It loses because a new skill is listed name-only, the user already ships codedna, and codedna's README is the actual distribution channel; `docdna` next to `codedna` in a listing is self-explaining in a way `docdebt` is not. Flagged as open question 1 because the reasoning is close enough that the user should confirm.

**"Add ~28 more document classes at v1.0" (completeness, Part D).** Half accepted. The P0 items are in the catalog: public privacy notice, RoPA, ToS, DPA and subprocessor list, hardening baseline, BIA, control inheritance, crypto inventory, key management, identity lifecycle, audit logging, trust pack, DR exercise records, status comms, AI Act Article 50 disclosure, data quality report, export control, records retention, and OSS contribution policy. **None of them get a template.** The P2 list (FinOps showback, localization plan, partner sandbox guide, insurance certificates, trademark policy, and the rest) is out entirely at v1.0. A catalog that grows faster than its maintainer is the same failure as a doc set that grows faster than its owner.

**"Add `audiences` plus per-section `zoom` maps and render an executive view" (completeness, Part B).** The `audiences` array ships. The zoom map and the renderer do not. Section-level audience tagging on `design.architecture` and `assure.control-mapping` is a real idea, and building a projection nobody has asked for is exactly the theater the skill refuses. Ship the data, defer the view, and revisit when a user asks for the executive rollup by name.

**"Make `embedded-device` and `research-artifact` primaries but keep `regulated` as one overlay with jurisdiction sub-flags" (completeness, Part C).** The two primaries are accepted. The rest of the same finding argued that health, payments, safety-critical, and air-gapped should be separate overlays rather than sub-flags of `regulated`. Accepted for health, payments, and safety-critical. **Rejected for `air-gapped-classified`**, which is out at v1.0: it changes the evidence *collection procedure* (an air-gapped repo cannot fetch CVE feeds or run SBOM tooling), not just the document list, and a design that has not modelled that should not ship a half version of it.

**"Trigger accuracy is neutral between one repo and two" (architecture design, section 1).** Rejected outright, and the product critique is right about why. It is neutral between one repo and two; it is decisively **not** neutral between one skill and two, because the per-skill description cap is 1536 characters and a merged description exceeds it. The architecture doc reached the right packaging verdict through a wrong argument, and the corrected argument also forces both descriptions down to roughly 400 characters, which the original design did not contemplate.

**"The scanner's JSON is safe to paste into a report" (architecture design, section 9.1).** Rejected. A regex-plus-entropy redactor over 160-character lines has false negatives, and a safety claim invites someone to paste it into a ticket. `text` is omitted entirely for secret-bearing paths and the phrasing is "review before sharing".
