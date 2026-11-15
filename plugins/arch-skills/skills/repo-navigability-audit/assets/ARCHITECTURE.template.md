# Architecture

<!-- A short map of the code, not a full design document. Name things a reader can search for.
     Keep it true: update it in the same PR that changes a boundary. -->

## Bird's-eye view
<three to five sentences: inputs, main flow, outputs, main data stores>

## Modules
| Module | Owns (the decision it hides) | Public entry | Depends on |
|---|---|---|---|
| `<path>` | <e.g. pricing rules> | `<path/index.ts>` | <modules> |

## Dependency rules
- Dependencies point toward `<domain module>`; it imports no framework, database, HTTP or LLM SDK.
- No cycles between modules.
- Enforced by: `<tool and config path>`

## Cross-cutting concerns
- Errors: <how errors are typed and propagated>
- Logging and tracing: <where, which IDs>
- Configuration and feature toggles: <where; toggles have owners and removal dates>

## Invariants
- <invariant> (ADR-NNNN)

## Glossary
| Term | Meaning | Not to be confused with |
|---|---|---|
| <term> | <one line> | <synonym we do not use> |
