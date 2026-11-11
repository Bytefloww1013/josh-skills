---
name: review-team
description: Use when the user asks for a code review by a fleet of specialized reviewer agents, wants multiple independent reviewer perspectives, or asks to run reviewers in single-pass or iterative fix-until-clean mode. Launches focused subagents for correctness, security, architecture, conventions, simplicity, UX, reliability, telemetry, testing, compatibility, and documentation review, plus the repo's own reviewer agents.
---

# Review Team

Run a fleet of specialized reviewer subagents against the same change. Each reviewer is intentionally unaware of the others and must stay within its assigned focus area.

Reviewer prompts live in `reviewers/`. Read only the reviewer files you plan to launch.

## Modes

- **single**: Default. Launch reviewers once, aggregate findings, deduplicate, and report the final review.
- **iterate**: Launch reviewers, fix accepted findings, rerun relevant reviewers, and repeat until the review is clean or the remaining findings are intentionally deferred.

If the user does not specify a mode, use **single**. Use **iterate** only when the user explicitly asks to keep fixing, make reviewers happy, or run until clean.

## Reviewer Set

Core reviewers:

- `reviewers/correctness-reviewer.md`
- `reviewers/security-abuse-reviewer.md`
- `reviewers/architecture-reviewer.md`
- `reviewers/code-quality-conventions-reviewer.md`
- `reviewers/simplicity-scope-reviewer.md`

Specialist reviewers:

- `reviewers/product-ux-accessibility-reviewer.md`
- `reviewers/performance-reliability-reviewer.md`
- `reviewers/telemetry-observability-reviewer.md`
- `reviewers/testing-strategy-reviewer.md`
- `reviewers/api-compatibility-reviewer.md`
- `reviewers/documentation-dx-reviewer.md`

Default to all core and specialist reviewers when the user asks for the full team. For narrower requests, launch only the relevant ones.

Repo reviewers: the repo's own reviewer agents, one per `.claude/agents/*-reviewer.md` file, if any. Each file's frontmatter `description` says which changes call for it. With the full team or a narrow request, in either mode, also launch every repo reviewer whose trigger the change meets.

## Launch Pattern

For each reviewer subagent, provide:

1. The exact reviewer prompt from its Markdown file.
2. The task description, PR/issue context, or user request.
3. The diff or changed files to review.
4. Any test results, logs, screenshots, or relevant repository context.

Add this wrapper to every reviewer prompt:

```text
You are one reviewer in a fleet of independent code review agents. You cannot see the other reviewers. Stay strictly within your assigned role. Return only concrete, actionable findings with file and line references. If you find no issues in your area, say so clearly. Do not provide general commentary, praise, summaries, or duplicate concerns outside your mandate.
```

Launch a repo reviewer as its own agent type, named by its file's frontmatter `name`: its file already holds its rules and its report's shape, so give it only the wrapper, the base the change is compared with, and the diff or changed files. If the session doesn't offer that agent type yet (it was added after the session started), launch a general-purpose subagent with the file's body as its prompt instead.

Prefer running independent reviewers in parallel. Do not ask multiple reviewers to solve the same broad task in the same way; their reviewer prompt is their boundary.

## Aggregation

After reviewers finish:

1. Merge duplicate findings.
2. Drop findings that lack a concrete failure mode, user impact, security risk, or maintenance cost.
3. Resolve conflicts using the codebase, tests, and stated requirements as evidence.
4. Rank findings by severity and practical importance.
5. Present findings first, with file and line references.

The final review should not expose raw reviewer transcripts unless the user asks for them.

## Iterate Mode

In **iterate** mode:

1. Run the initial reviewer set.
2. Decide which findings are valid and should be fixed.
3. Implement fixes directly.
4. Run tests or checks appropriate to the changes.
5. Rerun only the reviewers relevant to the changed areas or unresolved findings.
6. Continue until no actionable findings remain, or until any remaining findings are explicitly documented as out of scope, false positives, or accepted tradeoffs.

Keep the user informed between iterations. Do not loop indefinitely; stop when additional iterations are not producing material new findings.

## Final Response

For **single** mode, return the aggregated review.

For **iterate** mode, return:

- What was fixed.
- What verification ran.
- Which reviewers were rerun.
- Any remaining findings or accepted tradeoffs.
