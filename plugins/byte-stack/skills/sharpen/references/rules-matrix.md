# Token-Hygiene and ASD-STE100 Rules Matrix

Use this reference to decide what to delete, what to rewrite, and what to protect during sharpening.

## 1. Context-Hygiene Priority Order

Cut noise from largest scope to smallest scope:

1. **Irrelevant passages and semantic distractors:** Remove off-topic backstory, corporate mission fluff, duplicate paragraphs, and anecdotes that do not alter execution.
2. **Convoluted prose and passive chains:** Break multi-clause sentences into single-rule active statements.
3. **Conversational fillers and command hedges:** Strip social padding and uncertain phrasing from directives.
4. **Redundant explanations:** Replace multi-sentence descriptions of known patterns with exact Technical Names or Leading Words.

## 2. Word-Removal Safety Matrix

| Word Category | Examples | Safe to Remove? | Action Rule |
| :--- | :--- | :--- | :--- |
| **Conversational Fillers** | `actually`, `obviously`, `clearly`, `honestly`, `just`, `basically`, `kindly`, `please note that` | **Yes** | Delete. These tokens add social tone without task logic. |
| **Weak Intensifiers** | `very`, `really`, `so`, `quite`, `extremely`, `super`, `totally` | **Usually** | Delete, or replace with an exact metric if the source prompt states one. |
| **Certainty Hedges (in Instructions)** | `maybe`, `probably`, `definitely`, `perhaps`, `hopefully`, `try to` | **Yes (rewrite)** | Delete from directives. Convert into a direct imperative command or an explicit conditional rule. |
| **Certainty Hedges (in Source Data)** | `maybe`, `probably`, `likely`, `possibly`, `allegedly` inside quotes, logs, or tickets | **No** | Keep verbatim. Stripping hedges from source text turns guesses into false facts. |
| **Threshold Modifiers** | `too`, `almost`, `nearly`, `enough`, `at least`, `at most`, `only`, `exactly` | **No** | Keep. Changing *"almost full"* to *"full"* breaks pass/fail logic. |
| **Negations & Question Words** | `not`, `never`, `no`, `without`, `except`, `unless`, `why`, `when` | **No** | Keep. Dropping one negation reverses prompt logic. |

## 3. ASD-STE100 Grammar Rules for Prompts

Apply Simplified Technical English principles to all instructional text:

* **Sentence length limits:**
  * Procedural instructions: **20 words maximum** per sentence.
  * Descriptive context: **25 words maximum** per sentence.
* **Active voice:** Name the actor or use direct imperative commands (*"Validate the JSON payload"* instead of *"The JSON payload should be validated"*).
* **One idea per sentence:** Split compound rules joined by *"and furthermore"* or *"while also"* into separate numbered items.
* **Exact action verbs:** Replace weak verbs with concrete actions:

| Weak Verb | Replace With |
| :--- | :--- |
| `handle` / `deal with` | `validate`, `parse`, `catch`, `reject`, `retry`, `route` |
| `manage` | `create`, `update`, `delete`, `store`, `schedule` |
| `make sure` | `verify`, `confirm`, `enforce`, `require` |
| `look at` | `inspect`, `read`, `audit`, `analyze`, `compare` |
| `utilize` / `leverage` | `use`, `call`, `apply`, `run` |

## 4. Technical Names vs. Convoluted Jargon

* **Keep exact Technical Names:** Retain precise domain terms, protocols, headers, libraries, and data structures (`PostgreSQL`, `HTTP 429`, `Idempotency-Key`, `exponential backoff`, `stderr`). Models map exact technical terms directly to specialized weights in fewer tokens than plain-English paraphrases.
* **Cut corporate buzzwords:** Remove empty modifiers (`synergistic`, `holistic`, `best-in-class`, `seamlessly`, `empower`, `world-class`, `strategic utilization`).
* **Disambiguate overloaded terms:** If a niche or domain-specific term has two conflicting meanings in context, define it once in a single short sentence.

## 5. Protected Elements (Never Corrupt)

Never alter the syntax, casing, or meaning of:
* Fenced code blocks and inline code literals
* File paths, URLs, CLI flags, and environment variables
* Template placeholders (`{{var}}`, `$ARGUMENTS`, `${ENV_VAR}`)
* Regular expressions, JSON/YAML schemas, and SQL snippets
* Existing YAML frontmatter (`---`) unless explicitly asked to rewrite it
