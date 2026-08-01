# gitignored-paths

Every path this file names on purpose is one the repository ignores. Naming them is the whole point
of the instructions: the reader has to create the secrets file, install the dependencies, and read
the build output. None of them is a broken reference.

## Setup

Copy the sample settings into `web/.env.local` and fill in the keys. The file is ignored, so it
never reaches the repository.

Install the dependencies. That writes `web/node_modules`, which is also ignored.

```sh
bun install
```

Build the client. The bundle lands in `web/dist`.

```sh
bun run build
```

## Plan

The delivery plan is [web/.godplans/PLAN.md](web/.godplans/PLAN.md). It sits in a dot directory,
which docdna prunes out of the file index, but it is on disk and the link resolves. The index
decides what docdna reads. The filesystem decides what exists.

## Known broken reference

The onboarding notes used to live at [web/src/onboarding.js](web/src/onboarding.js). That file was
deleted and nothing replaced it, so this link is genuinely stale and docdna should say so.
