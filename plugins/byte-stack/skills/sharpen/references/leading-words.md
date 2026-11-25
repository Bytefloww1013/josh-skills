# Leading Words (Leitwörter) Reference

Leading words are concise, high-signal domain terms that anchor agent behavior using concepts already present in model pretraining. Effective leading words appear in reasoning traces and keep execution consistent across steps.

> **Important: Examples Only.** The table below shows illustrative examples, not a closed or exhaustive vocabulary. Choose any well-established, high-signal term that accurately fits the prompt's domain or the repository's `GLOSSARY.md`.

## Selection Criteria for Any Domain

Use a candidate Leading Word only when it passes all three checks:

1. **Established meaning:** Standard in domain literature or defined in the repo's `GLOSSARY.md`.
2. **High compression:** Replaces a multi-sentence explanation with 1 to 4 exact words.
3. **Low ambiguity:** Carries one clear meaning in the current context (add a 1-sentence definition if overloaded).

## Dual Role in Skills and Prompts

1. **Execution Anchor (Body):** Replace verbose behavioral explanations with one exact term so the agent sustains consistent behavior across steps.
2. **Routing Signal (Descriptions and Pointers):** Include the same term in skill descriptions, frontmatter, or reference pointers so agents trigger the right skill or doc.

## Illustrative Examples (Non-Exhaustive)

| Domain | Example Leading Words | Replaces Verbose Prose About... |
| :--- | :--- | :--- |
| **Software & Architecture** | `tracer bullets` / `vertical slice`, `deep modules`, `test seams` | Building one thin end-to-end working path instead of layer by layer; minimal public interfaces hiding complexity; mockable boundaries for testing. |
| **Planning & Alignment** | `frontier`, `fog of war` | Resolving immediate known decisions without over-planning uncertain future steps. |
| **Teaching & Communication** | `zone of proximal development` | Pitching explanations just above current skill level without boring or overwhelming the learner. |
| **Migrations & Reliability** | `expand-and-contract`, `strangler fig`, `circuit breaker` | Zero-downtime schema changes; incremental legacy replacement; failing fast when dependencies degrade. |

Draw freely from any other domain's canonical vocabulary (for example: security, data engineering, UX, finance, DevOps, legal, or operations) whenever a term meets the three selection criteria above.

## Vocabulary Consistency Rule

Inconsistent terminology causes inconsistent agent behavior. Never mix synonyms for the same concept in one prompt (for example: `user`, `learner`, and `student`, or `billing log` and `transaction table`). Pick one canonical term—preferring the repo's `GLOSSARY.md`—and apply it everywhere.

## Repository `GLOSSARY.md` Starter Template

When no `GLOSSARY.md` exists at the repository root and the user accepts creation, generate `GLOSSARY.md` with this structure pre-filled from the current prompt:

```markdown
# Project Glossary

Canonical terms and Leading Words for prompts, specs, and code in this repository. Use these exact terms instead of synonyms.

| Term | Meaning / Behavioral Intent | Avoid Synonyms |
| :--- | :--- | :--- |
| `<Term>` | `<1-sentence definition or expected agent behavior>` | `<replaced words>` |
```
