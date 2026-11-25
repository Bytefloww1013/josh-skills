---
name: sharpen
description: Sharpen, compress, and deepen prompts using ASD-STE100 grammar, token-hygiene rules, repo GLOSSARY.md terms, Leading Words (Leitwörter), and a 4-point depth audit (--deep). Use when the user invokes /sharpen or asks to clean, compress, deepen, rewrite, or optimize a prompt, agent instruction, or skill file.
argument-hint: "[--in <file>] [--out <file>] [--deep] [--noguard] [<raw prompt>]"
allowed-tools:
  - Read
  - Write
  - Glob
---

# sharpen

Rewrite a prompt or skill file to cut token noise, enforce consistent vocabulary, and improve agent execution.

## 1. Parse Arguments and Select Modes

Parse `$ARGUMENTS` for `--in <path>`, `--out <path>`, `--deep`, `--noguard`, and raw prompt text. Support quoted paths with spaces.

**Output Modes:**
1. **Chat Mode (default):** No `--in` and no `--out`. Output the final sharpened prompt in Markdown in chat.
2. **Input File Mode (`--in <path>` only):** Read `<path>`. Strip the file extension from `<path>` to get `<stem>`. Write only the sharpened prompt Markdown to `<stem>-sharpened.md`.
3. **Explicit Output Mode (`--out <path>` with `--in <path>` or raw prompt):** Read the input source. Write only the sharpened prompt Markdown to `<path>`.

**Depth Mode:**
* **Lossless Mode (default):** Preserve exact original scope and requirements. Invent zero new requirements.
* **Deep Mode (`--deep`):** Run the 4-Point Depth Audit (Step 3) before rewriting. Make the task **deeper, not bigger** by raising rigor, raw inputs, exact methods/tools, and external verification without adding unrelated scope.

**Draft Guard Mode:**
* **Guarded (default):** Present the sharpened draft (and the 4-Point Depth Audit if `--deep` is set) in chat first. Do not write any output files until the user accepts.
* **Unguarded (`--noguard`):** Skip the draft review. Execute the selected output mode immediately.

**I/O Guardrails:**
* Stop and report an error when `--in` points to a missing file.
* Stop and ask for confirmation when the output path matches the `--in` path.
* Keep existing YAML frontmatter (`---`) intact unless the user asks to edit it.
* Write zero commentary or audit notes to output files. In file modes, write only the sharpened prompt to disk and print the 1-line summary (plus the 4-Point Depth Audit if `--deep` is set) in chat.

## 2. Load Reference Rules and Check the Repo Glossary

1. Read `references/rules-matrix.md` before rewriting complex prompts.
2. Read `references/leading-words.md` when sharpening agent instructions, system prompts, or skill files.
3. Read `references/depth-audit.md` when `--deep` is set or when pivoting a rejected draft toward deeper rigor.
4. Read `references/examples.md` when the prompt contains quoted source data, code blocks, or nested conditionals.
5. Check the current repository or project for a glossary in these two places, in order: `GLOSSARY.md` at the root, then `docs/references/project-glossary.md`. Use the first file that exists and is not empty. Every later mention of `GLOSSARY.md` in this skill means the file found here.
   * **If a glossary exists:** Read it. Identify canonical project terms, definitions, and Leading Words that can tighten or clarify the prompt.
   * **If neither file exists or both are empty:**
     * In **Guarded mode**: Ask the user if a glossary exists at another path. If not, offer to create `GLOSSARY.md` at the repo or project root.
     * In **Unguarded mode (`--noguard`)**: Complete the sharpening output without blocking. Then inform the user in chat that no glossary was found at either path, ask if one exists elsewhere, and offer to create `GLOSSARY.md` at the repo root.
   * **If the user provides an alternate path:** Read that glossary and apply its terms before finalizing.
   * **If the user accepts creation:** Create `GLOSSARY.md` at the repo or project root using the starter format in `references/leading-words.md`, pre-filled with the key terms from the current prompt.

## 3. Run the 4-Point Depth Audit (`--deep` Only)

Skip this step in Lossless Mode. When `--deep` is active, complete these four points **before** rewriting the prompt:

1. **Expert Gap:** State what a top professional in this field would do here that the prompt does not ask for.
2. **Rawest Material:** Name the rawest primary material they would start from instead of pre-digested summaries.
3. **Specific Methods and Tools:** Name the exact methods, standards, and tools they would use.
4. **External Verification:** State what—other than the user or the AI—proves the result is right.

**Depth Guardrail:** Make the task **deeper, not bigger**. Upgrade primary inputs, analytical rigor, and objective verification. Do not add unrelated deliverables or expand project scope.

## 4. Run the Sharpening Pipeline

Apply these steps in strict order:

1. **Cut irrelevant chunks first.** Delete off-topic backstory, social pleasantries, duplicate rules, and semantic distractors before editing single words.
2. **Lock protected elements.** Keep code blocks, file paths, schemas, regexes, placeholders (`{{var}}`, `$ARGUMENTS`), negations (`not`, `never`, `no`), and threshold words (`too`, `almost`, `nearly`, `enough`, `at least`, `at most`) unchanged in meaning.
3. **Filter low-value words.**
   * Delete conversational fillers (`actually`, `obviously`, `clearly`, `honestly`, `just`, `basically`, `kindly`).
   * Delete weak intensifiers (`very`, `really`, `so`, `quite`, `extremely`) or replace them with explicit metrics from the prompt.
   * Delete certainty hedges (`maybe`, `probably`, `definitely`, `perhaps`) from **instructions**. Convert them into direct commands or explicit optional rules.
   * Keep certainty hedges inside **embedded source data, quotes, or logs** so guesses do not become false facts.
4. **Apply ASD-STE100 grammar to instructions.**
   * Keep instructional sentences at 20 words or fewer, and descriptions at 25 words or fewer.
   * Use active voice. Start each command with a direct imperative verb.
   * Put one idea or rule in each sentence.
   * Replace vague verbs (`handle`, `manage`, `deal with`) with exact action verbs (`validate`, `parse`, `reject`, `return`).
5. **Apply Leading Words (`Leitwörter`), Depth Findings, and Glossary Consistency.**
   * In `--deep` mode, rewrite the prompt to explicitly require the Expert Gap rigor, Rawest Material, Specific Methods/Tools, and External Verification from Step 3.
   * Replace verbose behavioral explanations with concise, high-signal terms native to the prompt's domain.
   * Treat the terms in `references/leading-words.md` as **illustrative examples only**, not a closed list. Draw freely from established literature in the relevant field (systems design, security, UX, finance, DevOps, education) and from `GLOSSARY.md`.
   * Keep exact Technical Names (`PostgreSQL`, `HTTP 429`, `Idempotency-Key`). Add a 1-sentence definition only when a term has conflicting meanings across domains.
   * Place key Leading Words in **both** the body (to anchor execution and reasoning traces) and the metadata/description (to trigger the right skill or reference) when sharpening skill files.
   * Normalize synonyms across the entire prompt so one concept always uses one term. Prefer exact `GLOSSARY.md` terms over synonyms.
6. **Format for fast scanning.**
   * Keep short prompts (under 5 rules) compact without unnecessary headings.
   * Structure multi-part prompts with clear Markdown headings (`## Goal`, `## Inputs`, `## Rules`, `## External Verification`, `## Output Format`) and numbered lists for ordered steps.

## 5. Verify Before Presenting

Confirm every item before presenting the draft or writing the final output:

* Every original requirement, edge case, negation, and threshold remains intact.
* **In Lossless Mode:** Zero new requirements, assumptions, or facts were invented.
* **In Deep Mode (`--deep`):** Every added requirement traces directly to the 4-Point Depth Audit, and task scope stayed focused ("deeper, not bigger").
* Every Leading Word accurately matches the intent of the prose it replaced.
* Every applicable term aligns with `GLOSSARY.md` (when present) and stays consistent across the prompt.
* Every instructional sentence uses active voice and stays concise.

## 6. Run the Draft Review Guard (Skip Only With `--noguard`)

Unless `--noguard` is present, stop before finalizing output and present the draft in chat:

1. If `--deep` is active, display the 4-Point Depth Audit first.
2. Show the proposed sharpened prompt in a Markdown block.
3. Add a brief summary listing the word count change, Leading Words applied, and `GLOSSARY.md` status (terms reused, or missing-glossary prompt).
4. Ask the user to **accept**, **refine**, or **reject** the draft.

**Handle the user's response:**
* **Accept:** Execute the selected output mode (`chat`, `--in`, or `--out`). Create `GLOSSARY.md` if the user agreed to it.
* **Refine:** Apply the user's adjustments (including any alternate glossary path or audit edits), re-run Step 5 verification, and present the updated draft or finalize if approved.
* **Reject / Deny:** Do not make minor wording tweaks. Select a **new angle of attack** (for example: escalate to the 4-Point Depth Audit when the prompt feels shallow, step back from `--deep` to Lossless Mode if it became too prescriptive, replace abstract Leading Words with explicit step-by-step rules, or change structure from checklist to constraint spec) and present a fresh draft. Repeat until accepted.
