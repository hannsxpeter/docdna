# Prose discipline

Normative for every document DocDNA writes. Read this after the evidence pass has accepted the draft.
Evidence determines what may be said. This reference determines whether the accepted facts are written
plainly enough to keep.

This guidance is adapted from the pstack `unslop` skill. The source and MIT notice are recorded in
[`third-party-notices.md`](third-party-notices.md).

## The constrained edit

Edit only the prose. Preserve every fact, citation, identifier, path, command, number, table relationship,
frontmatter value, and GAP marker. The edit may shorten, split, reorder, or restate a supported claim. It
may not add a fact, inference, opinion, promise, or attribution.

Run the evidence verifier again if the edit changes anything. A cleaner sentence with a broken citation is
still a failed document.

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
chatbot phrases, promotional terms, ornate substitutes for `is`, formulaic contrasts, generic endings,
and likely title-case headings. It ignores frontmatter, fenced code, inline code, HTML comments, and link
destinations. It never changes a file and never gates CI.

The checker cannot judge active voice, sentence density, synonym cycling, false ranges, factual
specificity, or whether a proper name explains capitalization. Review those in context. A pattern match is
a prompt to read the sentence, not permission to rewrite it automatically.
