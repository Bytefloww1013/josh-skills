---
name: byteflow-new-thing
description: Start any new feature or task the ByteFlow way - grill the user until Task, Guardrails and Definition of Done are nailed down, swap plain-language explanations for leading words, build deterministic pass/fail scripts, keep CLAUDE.md a lean index, record a phased plan in ./docs, then hand the user an exact /goal line and implement until the scripted checks pass.
argument-hint: "<what you want to build or do>"
disable-model-invocation: true
---

# /byteflow-new-thing

Request: $ARGUMENTS

Follow the steps in order. Never skip an approval gate. The user's choice is final once they say they want to keep it.

Bundled files (use them, don't rewrite them):
- `${CLAUDE_SKILL_DIR}/scripts/check-env.(ps1|sh)` - OS, shells, whether hooks (and so `/goal`) are disabled
- `${CLAUDE_SKILL_DIR}/scripts/check-claudemd.(ps1|sh) [path]` - CLAUDE.md size + required sections
- `${CLAUDE_SKILL_DIR}/scripts/check-plan.(ps1|sh) <plan.md>` - unchecked slices, next slice, Decisions present
- `${CLAUDE_SKILL_DIR}/templates/` - `implementation.md`, `CLAUDE.md`, `verify-done.ps1`, `verify-done.sh`

Script runner: on Windows run `pwsh -NoProfile -File <script>.ps1`; on macOS/Linux run `bash <script>.sh`. Every script prints one `PASS:`/`FAIL:`/`WARN:` line per check and exits 0 (all pass) or 1 (any FAIL).

Generated files live in the project root:
- `./docs/<slug>-implementation.md` - the plan (slug = kebab-case feature name)
- `./docs/verify/` - validation and helper scripts built in Step 5
- `./CLAUDE.md` - stays at the root (Claude only auto-loads it there)

---

## Step 0 - Preflight

1. Run `check-env`. Note the OS and the shell to write scripts in. If it reports hooks disabled, warn the user now that `/goal` will not work and the plan will run without it.
2. Look for `./docs/*-implementation.md`. If one matches this request, run `check-plan` on it and offer: **resume** at the first unchecked slice (skip to Step 8) or **start fresh**.

## Step 1 - Grill (Tenet 1)

Goal: three parts, each concrete enough to test.

| Part | Must answer |
|---|---|
| **Task** | What is being built or done, for whom, and what is explicitly out of scope? |
| **Guardrails** | What must not change, what must never be done (send, delete, publish, spend), which files/systems are off limits, what needs approval first? |
| **Definition of Done** | What gets verified, what does sufficient output look like, how will Claude know it is finished? |

How to grill:
- Use AskUserQuestion, at most 4 questions per batch. Put your recommended answer first with "(Recommended)" and its pros/cons in the option description.
- **Push back once** on any answer that is vague, untestable, or riskier than an alternative. Offer the alternative with pros and cons. If the user keeps their answer, record it and move on. Do not argue twice.
- Split the Definition of Done into two lists:
  - **Scripted** - checkable with an exit code (tests pass, file unchanged, endpoint returns 200, lint clean, file exists, count matches).
  - **Manual** - needs human judgment (looks right, copy reads well). Keep this list as short as possible; push to turn each item into a scripted check.
- Stop when all three parts are testable, or after 3 rounds. If gaps remain after 3 rounds, list them and ask whether to proceed with them recorded as open risks.

## Step 2 - Leading-word audit

Audit everything the user wrote during the request and grilling. Find every place they explained something from scratch that already has an established framework, term, pattern, or domain jargon. That established term is a **leading word**: shorter and more precise, and it pulls in the right shared knowledge.

Show the findings as a table:

| User's explanation (short quote) | Leading word | Why it fits |
|---|---|---|
| "if it fails, wait a bit longer each time before retrying" | exponential backoff | standard retry pattern with growing delay |
| "show the old data while fetching the new data in the background" | stale-while-revalidate | named HTTP/cache strategy |

Rules:
- Only map terms you are confident are standard. If unsure, say so in the "Why" column.
- If a term changes meaning (it implies more or less than the user said), flag it instead of silently swapping.
- After the user confirms or vetoes each row, use the confirmed leading words, not the long explanations, everywhere from now on: the Decisions in the plan, the `/goal` line, CLAUDE.md, script names and comments.
- Record confirmed rows in the plan's **Leading words** section.

Then show a one-screen summary of Task / Guardrails / DoD (scripted + manual) in leading-word form and get approval.

## Step 3 - Script analysis (Tenet 2)

List every candidate for a deterministic script:
1. **Validation** - each Scripted DoD item and each checkable Guardrail (e.g. "template unchanged" -> hash or `git diff --quiet` check).
2. **Repeated deterministic work** - anything the plan will do more than about twice the same way (seed data, regenerate fixtures, run a build + test combo, format + lint).

Language: Windows -> PowerShell 7; macOS/Linux -> Bash. Use Python or JS/TS instead when the check needs real parsing (JSON/YAML/AST) or the project already standardises on it. If the project is used on more than one OS, offer to write both `.ps1` and `.sh`.

Present the list (name, purpose, language, PASS condition). **Get approval before building anything.**

## Step 4 - CLAUDE.md as a lean index (Tenet 4)

Ask the user what belongs in each section, then fill gaps from what you learned:
- **TOOLS AND COMMANDS** - tools, commands, skills, MCP servers Claude can't guess (include the `./docs/verify/` scripts).
- **WORKFLOWS** - only workflows that deviate from common practice, one line each.
- **GOTCHAS** - things Claude has got wrong more than once, each with the correct behaviour.

Rules: keep it under 200 lines; no code walkthroughs, no history, nothing Claude can read from the code. If no CLAUDE.md exists, start from `templates/CLAUDE.md`; if one exists, add the three sections without deleting the user's content. Show the diff, **get approval**, write it, run `check-claudemd`.

**Standing rule for the rest of the session:** whenever a new tool/command, an unusual workflow, or a repeated mistake comes up, ask yourself whether CLAUDE.md needs an update, and propose it.

## Step 5 - Plan + scripts

1. Write `./docs/<slug>-implementation.md` from `templates/implementation.md`:
   - Decisions (Task, Guardrails, DoD scripted + manual, open risks) and Leading words from Steps 1-2.
   - Numbered phases made of small slices; one `- [ ]` checkbox per slice. A slice is one reviewable change.
   - The last phase is always "Verify": run `docs/verify/verify-done.*` and confirm the manual items.
   - Run `check-plan` on it (expect FAIL for unchecked slices; it must not FAIL on missing Decisions).
2. Build the approved scripts in `./docs/verify/`. Start `verify-done` from `templates/verify-done.(ps1|sh)` - one check per Scripted DoD item and checkable Guardrail.
3. Run `verify-done` once now. It should FAIL on the unfinished work. A check that already passes before any work is done proves nothing: fix or explain it.

## Step 6 - Propose the /goal (Tenet 3)

`/goal` is a built-in command the **user** types; you cannot set it. After each turn a small model judges the condition from the conversation, so the turn limit is a soft instruction, not a hard cap. Anchor the goal to the script's exit code.

Write one line that has all four parts:
1. **One explicit end state.**
2. **Proof** - the exact command and that its PASS output is shown in chat.
3. **What must not change** - the Guardrails, in leading words.
4. **A turn limit** - and what to do when it is hit (stop and report blockers).

Format:
```
/goal <end state>; proven by `<verify-done command>` exiting 0 with its PASS lines shown in chat; <guardrails> unchanged; if manual DoD items remain, stop and ask the user; stop after <N> turns and report what is blocking.
```

Show the line, explain each part in one sentence, **get approval**, then tell the user to paste it. Remind them: `/goal` with no argument shows status, `/goal clear` stops it.

## Step 7 - Implement

- Work slice by slice in plan order. Tick `- [x]` in the plan as each slice is finished and checked, never before.
- After each phase: run `check-plan`, then decide whether CLAUDE.md needs new entries or pruning (stale tools, workflows no longer used, gotchas that no longer apply). Propose changes; run `check-claudemd` after any edit.
- Respect Guardrails at every step. If a slice would break one, stop and ask.
- Use the Step 3 helper scripts instead of repeating the work by hand.

## Step 8 - Done

Done means: `verify-done` exits 0 with output shown in chat, `check-plan` reports 0 unchecked slices, and the user has confirmed every manual DoD item. Report in a few lines: what was built, the passing output, open risks, and any CLAUDE.md changes made.
