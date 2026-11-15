# Fitness functions

Read this when you must turn a decision or a finding into an automated check.

A fitness function is an objective check of an architectural characteristic that runs in CI or in the agent's own loop (Ford, Parsons & Kua, *Building Evolutionary Architectures*, 2017; 2nd ed. with Sadalage, 2022). An invariant that exists only in a document will erode; agents read rules but do not reliably follow them under pressure.

## Writing one

Each fitness function has: an ID tied to its ADR (`FF-0012-1`), the invariant in one sentence, the tool and rule or command, where it runs (pre-commit, CI, agent loop), and what happens on failure (block merge, warn).

Prefer, in order: an existing rule in a tool the repo already uses; a config change to that tool; a small test in the repo's own test framework; a new tool only if nothing else works. Name the exact rule. "Add a linter" is not a fitness function.

## Tool menu by concern

Only suggest a tool that fits the repo's language and existing setup. Check `package.json`, `pyproject.toml`, `go.mod`, build files first.

| Concern | Python | JS / TS | JVM | Other / any |
|---|---|---|---|---|
| Module boundaries and layers | import-linter, Tach | dependency-cruiser, eslint-plugin-boundaries, Nx module boundaries | ArchUnit | Go: depguard (golangci-lint); .NET: ArchUnitNET, NetArchTest |
| Cycles | import-linter | madge --circular, dependency-cruiser | ArchUnit slices | |
| Duplication | jscpd, PMD CPD | jscpd | PMD CPD | jscpd (many languages) |
| Complexity | radon, ruff (C901), lizard | ESLint `complexity`, lizard | PMD, lizard | lizard (many languages) |
| API contracts | schemathesis | Pact, oasdiff | Pact, Spring Cloud Contract | oasdiff for OpenAPI, buf breaking for protobuf |
| Schema migrations | | | | squawk (Postgres), atlas lint |
| Test integrity | Protect test files via CODEOWNERS or a CI check that fails when tests and source change in the same agent PR without a reviewer label; mutation testing (mutmut, Stryker, PIT) to catch weakened assertions | | | |
| Error handling | ruff (BLE001 blind except, S110 try-except-pass), pylint W0702/W0718 | ESLint `no-empty`, typescript-eslint `no-floating-promises` | Error Prone, SpotBugs | Go: errcheck |
| Toggle expiry | Small CI script that reads toggle config and fails past the removal date | | | |

## Example: import-linter contract (Python)

```ini
[importlinter:contract:billing-orders-boundary]
name = Billing uses only the Orders public API
type = forbidden
source_modules = app.billing
forbidden_modules = app.orders.internal
```

## Example: dependency-cruiser rule (JS/TS)

```js
{ name: "no-core-to-infra", severity: "error",
  from: { path: "^src/domain" },
  to:   { path: "^src/(infra|adapters)|node_modules/(pg|axios|openai)" } }
```

Verify rule syntax against the tool's docs before committing it; these are shapes, not tested configs.
