# DocDNA 1.4.0

DocDNA 1.4.0 adds local checks for the installed agent skill and a complete handoff path for one document
at a time.

## Know whether the installed skill can run

The new read-only Doctor loads the shared runtime registry, checks every registered resource, checks Python
compatibility, and validates the installed proof registry. Source checkouts and installed copies report their
different proof boundaries instead of presenting them as equivalent.

## Hand one bounded document packet to a fresh agent

Status returns one prioritized next action without writing. Backfill can produce a complete one-document
packet with the repository evidence, templates, output path, proof limits, and verification command needed
for a fresh agent context.

## Keep product claims attached to their evidence class

The proof registry keeps verified, attested, self-attested, refused, replayed, measured, adjudicated,
host-captured, and external-tool-dependent evidence distinct. CI validates both registries, compiles every
registered Python helper on Python 3.8 and current Python, and exercises Doctor, Proof, Status, packet,
Check, llms, and Wire from an isolated installed copy.

## Install

```sh
git clone --branch v1.4.0 --depth 1 https://github.com/hannsxpeter/docdna.git
cd docdna
./install.sh claude      # or: all | codex | cursor | windsurf
```

The installed Doctor and Proof checks validate structure and declared resources. They do not authenticate
installed bytes against a signed release manifest. An interrupted upgrade can also remove the prior install,
so keep the cloned checkout until the replacement passes Doctor. These limits are tracked for the first
post-release sprint.

See `CHANGELOG.md` for the complete 1.4.0 change list and `README.md` for the first-run guide.
