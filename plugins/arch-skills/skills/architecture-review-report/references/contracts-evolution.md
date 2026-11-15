# Contracts and data evolution

Read this when a decision or diff changes a database schema, an API, an event or message format, or a file format that something else reads.

## Expand and contract (parallel change)

Never rename or retype a field in place when anything else reads it. Three steps, each its own release:
1. **Expand:** add the new field, column, table or endpoint next to the old one. Write to both (or translate).
2. **Migrate:** move readers one at a time. Backfill data. Measure reads of the old shape.
3. **Contract:** remove the old shape only when reads are zero.

Source: Danilo Sato, "ParallelChange" (martinfowler.com, 2014); Ambler & Sadalage, *Refactoring Databases* (2006).

Red flags: a migration that drops or renames a column in the same release that changes the code; a "breaking change" note with no migration plan.

## Tolerant reader

Consumers read only the fields they need and ignore unknown fields (Fowler, "TolerantReader", 2011; Postel's robustness principle, RFC 761). Producers may then add fields without breaking anyone. Strict schema validation that rejects unknown fields on the consumer side breaks this; validate only what you use.

## Consumer-driven contract tests

Each consumer states what it needs from a provider as a test the provider runs (Pact is the common tool). Use at module or service boundaries where an agent may change one side. For OpenAPI, a breaking-change diff (for example `oasdiff breaking`) in CI catches removed fields and narrowed types.

## Transactional outbox

When a state change must also publish an event, write the state and an outbox row in one local transaction; a relay publishes from the outbox (Chris Richardson, microservices.io, "Transactional outbox"). This gives at-least-once delivery, so consumers must be idempotent. Red flag: writing to the DB and then calling the broker in the same request with no outbox (lost or phantom events: Timing and Value connascence across services).

## Versioning

- Additive changes need no new version if readers are tolerant.
- Removals and meaning changes need a new version or the expand/contract steps.
- A field that changes meaning but keeps its name is the worst case (Meaning connascence that tools cannot see). Give it a new name.

## Bi-temporal data (only where audit matters)

If the domain needs "what did we know, and when", store valid time and transaction time and make changes append-only (Snodgrass, *Developing Time-Oriented Database Applications in SQL*, 1999; Fowler, "Bitemporal History", 2021). Do not suggest this by default; it costs complexity.
