---
godpowers: 7
project: docdna
stage: build
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
- Maintenance pass after 1.4.0: code review, documentation drift, obsolete files, and the open installer
  finding. See PLAN.md.

## Next
- Finish the maintenance slices in PLAN.md, record the check, and merge to main.

## Risks
- [ ] medium: release installation is not bound to verifiable provenance (no signed tag, digest, or
  provenance; mutable CI runner and ShellCheck source), README install command and `.github/workflows/ci.yml`
- [ ] medium: installed runtime and proof bytes are not authenticated; Doctor and installed Proof pass after a
  same-user byte change, `skill/scripts/docdna_doctor.py` and `skill/scripts/docdna_proof.py`
- [ ] medium: installer failure can destroy the last working install (`rm -rf` before copy, no staging or
  rollback), `install.sh` `install_skill`
