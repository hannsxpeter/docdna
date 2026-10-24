---
godpowers: 7
project: docdna
stage: review
verify: "python3 -m unittest discover -s tests"
updated: 2026-10-08
---
# docdna

## Goal
docdna is a portable, stdlib-only coding-agent skill for people who own or inherit a codebase. Success is a
document ledger they can defend: every document ruled in or out with a cited reason, every generated claim
cited or marked as a gap, and CI proving that the published samples, counts, and generated files match the
code.

## Now
- Maintenance pass after 1.4.0 is merged: review fixes, shared claim engine and fs runners, installer
  staging, documentation drift, and doc-fact tests. Recorded under [Unreleased] in CHANGELOG.md.

## Next
- Cut 1.4.1 when the owner wants the fixes installable by tag (CONTRIBUTING.md, Cutting a release).
- Close the two Medium provenance risks with a signed release manifest that Doctor verifies.

## Risks
- [ ] medium: release installation is not bound to verifiable provenance (no signed tag, digest, or
  provenance for the released tree), README install command; the CI runner is now pinned to
  `ubuntu-24.04` and ShellCheck comes from that image
- [ ] medium: installed runtime and proof bytes are not authenticated; Doctor and installed Proof pass after a
  same-user byte change, `skill/scripts/docdna_doctor.py` and `skill/scripts/docdna_proof.py`
- [x] medium: installer failure can destroy the last working install (`rm -rf` before copy, no staging or
  rollback), `install.sh` `install_skill`; fixed by a staged, doctor-validated swap with rollback
- [x] high: a repository's own git config ran commands through docdna's git calls (`core.fsmonitor`,
  hooks, filter and diff drivers), `skill/scripts/docdna_fs.py` `run_in_root`; fixed in 1.4.1
- [x] medium: Check expanded a committed blob fully before its size bound, and the YAML/JSON key
  pattern was quadratic on long runs of spaces; fixed in 1.4.1
- [ ] low: the installer copies the source into itself when the destination sits inside the source
  checkout (`CLAUDE_SKILLS_DIR=$SRC/skill`); fails with "File name too long", source intact,
  `install.sh` `destination_holds_source`
- [ ] low: installer swap race: a same-user process that recreates the destination between the two
  `mv` calls gets the new install nested at `dest/new`, `install.sh` `install_skill`
- [ ] low: CI leaves `GITHUB_TOKEN` (`contents: read`) in `.git/config` while running repository code;
  add `persist-credentials: false`, `.github/workflows/ci.yml`
- [ ] low: the setup-python pin comment says `# v7` for the v7.0.0 SHA, `.github/workflows/ci.yml`
