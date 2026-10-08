# Decisions

Append-only. Newest last. To change a decision, add an entry that supersedes it.

## 2026-09-26: Move to the Godpowers 7 layout
Context: Godpowers 7 keeps one state file, a plan, this decision log, and an evidence ledger.
Decision: Archived the 6.x files under `.godpowers/archive/v6/`.
Why: Less state to keep in sync; gates are enforced by code instead of instructions.

## 2026-10-08: Remove the 6.x archive and the pre-release design notes
Context: `.godpowers/archive/v6/` held 1.4.0 launch records and a security report whose three open Medium
findings were the only live content. `docs/design/HANDOFF.md` asked to be deleted once the repository had
real documentation, and `docs/design/DOCDNA-DESIGN.md` was the 0.1 pre-implementation spec, superseded by
the shipped catalog, `skill/catalog/SCHEMA.md`, and `docs/HOW-IT-DECIDES.md`.
Decision: Deleted all three. The open findings now live under Risks in STATE.md.
Why: Stale planning text reads as current intent. Git history keeps every file at commit c34ae7d.
