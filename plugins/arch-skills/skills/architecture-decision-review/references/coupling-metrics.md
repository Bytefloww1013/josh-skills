# Coupling metrics and dependency direction

Read this when a decision adds, removes or reverses a dependency between modules, or when you need numbers for a module's stability.

## Metrics (Martin 2000, "Design Principles and Design Patterns"; Martin 2002, *Agile Software Development*)

| Metric | Meaning |
|---|---|
| Ca (afferent) | Number of other modules that depend on this module |
| Ce (efferent) | Number of other modules this module depends on |
| I = Ce / (Ca + Ce) | Instability, 0 = stable (hard to change, many depend on it), 1 = unstable (easy to change, nothing depends on it) |

Get them with the bundled script when the code is TypeScript, JavaScript or Python:

```
python3 scripts/coupling_metrics.py --root src --depth 1                    # table, one module per folder
python3 scripts/coupling_metrics.py --root . --module 'modules/*' --module kernel=server   # name the modules
python3 scripts/coupling_metrics.py --root src --json > base.json            # save
python3 scripts/coupling_metrics.py --root src --compare base.json           # what changed
```

Run `--help` first. It reads path aliases from `package.json` "imports" and tsconfig "paths", leaves generated files (`*.gen.ts`) out because a generated registry imports everything on purpose, and lists type-only edges apart (Connascence of Type, which may cross a boundary). In `--compare` output, read `new_cycle_edges` first: it names the edge that closed a cycle. Treat the output as a floor: the script cannot see dynamic imports with computed paths, DI containers, or other languages. For those, count by hand from imports or use a tool listed in fitness-functions.md.

## Principles

- **Acyclic Dependencies Principle (ADP).** No cycles between modules. A cycle makes the modules one unit for change, test and release.
- **Stable Dependencies Principle (SDP).** Depend in the direction of stability: I(dependent) >= I(dependency). A stable core that imports a volatile SDK wrapper passes every SDK change into the core.
- **Dependency Inversion Principle (DIP).** High-level policy does not depend on low-level detail; both depend on an abstraction owned by the policy side.
- **Hexagonal architecture / ports and adapters (Cockburn 2005).** The domain core has no imports of frameworks, databases, HTTP clients, queues or LLM SDKs. The core owns port interfaces. Adapters implement them. Source dependencies point inward.

## How to apply in a review

1. Draw the before and after dependency arrows for the touched modules (text is fine: `orders -> billing -> domain`).
2. Check each new arrow: does it point inward or toward a more stable module? Does it close a cycle?
3. If the core gains an import of infrastructure, that is Critical unless an ADR allows it.
4. If an arrow points to a less stable module, suggest an interface owned by the stable side (DIP), or move the code.
5. If metrics are not available, say "qualitative" and reason from imports you read.

## Red flags

- A "shared" or "common" module that everything imports and that imports many things (high Ca and high Ce).
- Types moved into a new shared module only to break a cycle, with no clear owner.
- A domain module importing `requests`, `axios`, an ORM, `openai`/`anthropic` SDKs, or a web framework.
