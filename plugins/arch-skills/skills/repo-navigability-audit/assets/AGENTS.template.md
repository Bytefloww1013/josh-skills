# AGENTS.md

<!-- Keep this file short. Every line is read at the start of every agent session.
     Put only what is specific to this repo. Link to details instead of copying them. -->

## What this is
<one or two sentences: what the system does and who uses it>

## Start here
- Map of the code: ARCHITECTURE.md
- Decisions and why: docs/adr/ (read the ADR before changing code that links to it)
- Golden-path feature to copy: <path/to/example-feature/>
- Golden-path test to copy: <path/to/example.test.ts>

## Commands
- Install: `<command>`
- Test (all): `<command>`
- Test (one file): `<command>`
- Lint and type check: `<command>`
- Architecture checks: `<command>` (must pass before a PR)

## Where things go
- New feature: `<features/<feature-name>/>`, following the golden path
- Shared domain types: `<path>` (read-only for feature work; changes need an ADR)
- Adapters for external services: `<path>`

## Rules that differ from the usual
- <rule> (why: <one line or ADR link>)
- Import other modules only through their public entry (`index.ts` / `__init__.py`).
- Do not edit tests to make them pass; if a test looks wrong, stop and say why.

## Do not touch
- `<path>`: <reason>
