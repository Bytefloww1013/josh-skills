### Autopilot-stack

Run the **Autopilot-full** playbook (`playbooks/autopilot-full.md`), but stop before the merge and hand the PRs to the user.

1. **In place of step 6, stop at green and reviewed.** Stop when each PR's checks pass at its current head and its review is reported. This is where a `/byte-gh-issue-claim <N> --auto` run ends anyway: it opens the PR, reports the URL and the `gh pr checks <pr>` status, and leaves the merge to the user. After the handoff, open no other PR without the user's say-so (`docs/directives/git-and-prs.md`). The merge is the user's, squash only, and that issue's local branch is deleted after it, as step 6 of Autopilot-full says (`docs/directives/git-and-prs.md`).
2. **Stacking is not established in bphs-connect.** No repo doc says how to stack PRs, and all 105 PRs target `main`. Branch every PR from `main`. If the user asks for a PR on top of another PR's branch, know what the workflows do:
   - PR checks and CI run only on PRs to `main`, so a PR based on another branch gets neither.
   - When its base changes to `main`, the `Start CI on a retargeted PR` job runs `gh workflow run CI --ref "$HEAD_REF"`. That tests the branch, not the PR merged into `main`.
   - A squash merge leaves the lower branch's commits off `main`.

**Reply:** list each PR with its link, its checks at the head, its review findings and its Door, in place of what merged. Each merge is the user's call: lay them out as the **ketchup** helper's action items.

Sources: docs/directives/plans.md, docs/directives/git-and-prs.md, docs/skills/byte-gh-issue-claim.md, .claude/skills/byte-gh-issue-claim/SKILL.md, .claude/skills/pr/SKILL.md, .github/workflows/pr-checks.yml, .github/workflows/super-linter.yml
