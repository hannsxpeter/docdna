# monorepo

A workspace repository with one manifest at the root and one in every package. The commands below
are declared in the root `package.json` and are meant to be run from the repository root, which is
where a reader of this file already is.

## Commands

Build every workspace:

```sh
bun run build
```

Run the language model output suite:

```sh
bun run test:llm-output
```

Cut a release bundle:

```sh
bun run release:package
```

Ship the built bundle to the hosts:

```sh
make deploy
```

Install the Python tooling that lives beside the workspaces:

```sh
pip install -e .
```

## Layout

- `apps/web` is the browser client.
- `apps/api` is the HTTP service.
- `packages/shared` is the code both of them import.
