# Prose discipline

Normative for every document DocDNA writes. Read this after the evidence pass has accepted the draft.
Evidence determines what may be said. This reference determines whether the accepted facts are written
plainly enough to keep.

This guidance is adapted from the pstack `unslop` skill. The source and MIT notice are recorded in
[`third-party-notices.md`](third-party-notices.md).

The narrow advisory catalog also draws on the
[`Humanizer`](https://github.com/Aboudjem/humanizer-skill/blob/main/skills/humanizer/SKILL.md)
pattern definitions for chatbot artifacts,
knowledge-cutoff disclaimers, diff-anchored writing, signposting, and clustered vocabulary. DocDNA keeps
only patterns that can be checked literally with useful restraint. It does not import Humanizer's
authorship scoring or rewriting behavior.

## The constrained edit

Edit only the prose. Preserve every fact, citation, identifier, path, command, number, table relationship,
frontmatter value, and GAP marker. The edit may shorten, split, reorder, or restate a supported claim. It
may not add a fact, inference, opinion, promise, or attribution.

Run the evidence verifier again if the edit changes anything. A cleaner sentence with a broken citation is
still a failed document.

Before running the evidence verifier, compare the protected inventory:

```sh
python3 skill/scripts/docdna_prose.py --compare before.md after.md
```

The command is read-only. Each input must be a regular file no larger than 5 MiB. Symlinks, directories,
FIFOs, devices, oversized files, and undecodable input are refused without reading an unbounded stream.
The command exits 0 when the protected inventory is unchanged, 1 when an item was added or removed, and 2
when an input is refused or cannot be read. Add `--json` for stable machine-readable output.

## What to keep

1. **Concrete mechanisms.** Name the file, symbol, command, input, output, or measured result. Describe what
   it does, not a feeling about it. A sentence that could move unchanged into another project's docs is
   paper theater and should be removed.
2. **Plain words.** Prefer `use` to `utilize`, `help` to `facilitate`, and `many` to `numerous`. Replace
   `serves as`, `stands as`, and `boasts` with `is`, `has`, or the action itself.
3. **Named actors.** Prefer active voice when the actor matters. `The loader parses the file` tells the
   reader more than `the file is parsed`. Passive voice is fine when the actor is unknown or irrelevant.
4. **One main idea per sentence.** Split a sentence when its reader must backtrack. Delete clauses that
   repeat the heading or merely announce the next clause.
5. **Stable terms.** Pick the repository's term and repeat it. Cycling through synonyms makes a reader
   wonder whether the words name different things.
6. **Named sources.** Replace vague attributions with a citation to the named source, or remove the claim.
   A phrase such as `experts believe` cannot satisfy the evidence rule.
7. **Direct framing.** Remove filler, promotional adjectives, generic conclusions, chat closings, and
   formulaic contrasts such as `not just X, but Y`. Start with the fact the reader needs.
8. **Sentence-case headings.** Capitalize a heading as a sentence unless it contains a proper name or an
   acronym whose spelling requires otherwise.

Vary sentence length when the material supports it. Do not force a list into three items, manufacture a
range between unrelated ideas, or add a synonym merely to avoid repetition.

## What not to import

Do not add first-person reactions, deliberate messiness, or unevidenced opinions to derived technical
documentation. Those devices can give an essay a voice, but here they create claims the repository did not
make. Do not apply a universal word blacklist, rewrite quoted source text, or change code and identifiers
to satisfy an editorial preference.

This is a writing-quality review, not an authorship test. Passing it does not show that a person wrote the
document. Failing it does not show that a model did.

## The advisory checker

`docdna_check.py --only prose` reports a small set of literal patterns: vague attributions, filler,
chatbot phrases, knowledge-cutoff disclaimers, promotional terms, ornate substitutes for `is`, formulaic
contrasts, generic endings, diff-anchored writing, signposting, clustered vocabulary, and likely
title-case headings. It ignores frontmatter, fenced code including fences inside block quotes, inline code
including code spans that cross lines within one paragraph, literal examples in quotation marks, HTML
comments, inline and reference-style link destinations, and CommonMark URI or email autolinks. An inline
destination is protected only when a syntactically plausible `[label](destination)` opener precedes it, so
a stray `](...)` remains visible prose. Brackets inside protected spans cannot supply that opener.
Multiline inline code stays within its Markdown paragraph block. It cannot cross an ATX heading, a change
in block quote depth, or a separate list item. Every masked character keeps its source position, so a
finding beside a protected span still reports its original line and column. The pass never changes a file
and never gates CI.

A single transition or watched vocabulary word is not a finding. Transitions and vocabulary require
recurrence or co-occurrence in the same paragraph. Diff-anchored language is allowed in changelog,
release-note, and migration paths, where edit history is the document's subject. Passive voice and
technical compounds are not inferred from syntax.

## Protected inventory comparison

The comparison inventories frontmatter values, citations, GAP markers, numbers, inline code, link targets,
fenced blocks, path-like tokens, and table shape. It reports exact additions and removals for each category.
This deterministic check catches protected facts and structures that a prose-only edit must not change.

An unchanged inventory is necessary but not sufficient. The command always returns an `unverified`
soft-inference review with causal, temporal, and quantitative questions. A person must review whether the
edit changed a reason, condition, sequence, duration, amount, scope, comparison, or limit. The command
never reports those relationships as verified.

The checker cannot judge active voice, sentence density, synonym cycling, false ranges, factual
specificity, authorship, or whether a proper name explains capitalization. Review those in context. A
pattern match is a prompt to read the sentence, not permission to rewrite it automatically.
