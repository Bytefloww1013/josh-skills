---
name: review-loop
description: Use when the user says "review loop", or when bmode's Opening a PR step requests a pre-push review.
---

# review-loop

This is a workflow for making your code changes more correct before (or
sometimes after) filing a pull request. tl;dr - use an independent reviewer to review
your code in a loop.

Make the most minimal possible changes to appease the reviewers. Be careful
of scope creep and don't be scared to push back.

## Budget

- Default: 3 rounds total. Round 1 is full. Later rounds check only
  changed instructions and code, and open findings.
- Extend to 5 only for security, permissions, auth, data loss, or
  state/concurrency, while a blocker or should stays open with evidence. Or when
  the user asks.
- Stop early on approval if only nits remain and the behavior is unchanged
  since review. Declined nits and edits that leave behavior unchanged need
  no new round on their own.
- One reviewer only. The reviewer must not start subagents or reviewers.
- Keep a ledger: id, severity, outcome, usage if returned. Never guess it.

## 1. Scope

Run `git status --short`. Do not stash, discard, or include unrelated
changes. Limit review to the change paths if they separate cleanly.
Otherwise stop and ask.

Identify the base. If an origin remote exists, fetch it first:

- PR: `gh pr view <n> --json baseRefName,headRefOid`. Check out the branch
  only if clean. Confirm `HEAD` is the PR head, or ahead only by this
  change. Base: `git merge-base HEAD origin/<baseRefName>`.
- Local: `git merge-base HEAD origin/<default-branch>`. No remote: a base
  the user names, or `HEAD` for uncommitted changes only.

The change is base to working tree in those paths, with untracked files.
Use one diff command all rounds. State intent and out-of-scope in 1-2
sentences. Run covering checks. Do not send code this change breaks. Note
missing or pre-failing checks in the brief.

## 2. Start a review

Use an available independent reviewer with access to the checkout, inheriting host defaults or honoring an explicit target. Follow the repository's policy. Report an unavailable requested target. If independent review is unavailable, label any self-review accordingly.

Give the reviewer the checkout, base, head, working changes, intent, scope and check results. Use this brief:

```text
Review the supplied change read-only. Examine:
    - broken callers
    - implicit state machines: contain deadends/bad states
    - mismatch with intent
Skip style unless it hides a bug. Hold to the smallest change. Flag code,
tests, or guards the intent does not need. Other paths, rare cases, small
perf, extra compat: nits.
blocker = intended case wrong. should = real bug callers will hit, in intent. nit = rest.
Use CHANGES if there is any blocker or should finding, and APPROVE otherwise.
Reply:
VERDICT: APPROVE or CHANGES
S1 [blocker|should|nit] <file>:<line> <claim>. Fix: <suggestion> (stable ids)
```

## 3. Answer findings

Check each finding and severity yourself. Another path, rare case, or
small cost is a nit, whatever label it came with.
Treat a verdict that conflicts with its reported findings as invalid.

- Agree: smallest fix. Prefer delete or narrow over new lock, cache,
  helper, or option. Fix the case that happened. Add one focused test
  that fails without the fix, if intent needs it.
- Disagree: say why, with evidence (file:line, test, output).
- Out of scope or nit: decline in one line. List as follow-up.

Update the ledger. Re-run checks and `git diff --shortstat <base>`. If
review grew the diff, cut first. Do not agree just to end the loop.

## 4. Next round

Start one only if budget remains and a blocker or should is open, behavior
changed (including workflow instructions in Markdown), or approval does not
cover the current behavior diff. Use a fresh
`delegate_task` in T3, or start a fresh native review. Send the round 1 brief,
the ledger (`fixed:` / `disagree:` / `declined:` + evidence), the same base
diff, and the change since last round. Ask the reviewer to review only open findings and
instructions or code changed since the last round.
Mark each old id `resolved` or `still open: <reason>`.

## 5. Stop and ship

Agreed: APPROVE on the current behavior diff, no blocker or should open,
no concern of your own. Stuck: an item stays disputed after two replies,
or budget ends. Show both sides in 2-3 lines each. The user decides.
Budget end is not approval.

Do not push during the loop. Push after agreement only if the user asked
to push, ship, or update the PR. When bmode runs the loop, return the
outcome to its playbook, whose push and PR rules apply instead. If you push to a PR, add above the model
blurb:

`Reviewed with review-loop: <N> rounds with <model>. Verdict: approved`.

Add `on <effort>` only if verified.

Report: rounds, model, what changed, diff size before/after, fixed and
declined findings with reasons, usage if exposed (else say not), pushed or not.
