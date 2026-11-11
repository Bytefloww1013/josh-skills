### Upgrade staging

**Rehearse on Staging through `scripts/staging.sh`, run each `**Stop:**` step only on the operator's go-ahead for that step, and end with a result block.**

Staging runs a committed ref on a production backup, on homelab, reached only over the tailnet (`docs/how-to/run-staging.md`). It is a full, unscrubbed copy of production, kept for rehearsing upgrades only (`docs/adr/0002-production-copy-as-staging.md`). That is the one exception to the real-backup rule, and the staging line in Autonomy (`SKILL.md`) holds what an agent may read of it.

1. **Name what you rehearse.** The ref and the backup it starts from:
   - For an upgrade, the Upgrade production playbook hands over the commit the VPS is at after `docs/how-to/upgrade-production.md` step 4 and the backup its step 2 took. Its step 7 rehearses that commit on that backup.
   - For a branch's migration (New migration playbook), `origin/<branch>` after a push and the newest nightly backup. Only committed code ships: the image is built from `git archive` of the ref (`docs/how-to/run-staging.md`, Guidance).
2. **Work on homelab, in `~/dev/bphs-connect`.** Every command in `docs/how-to/run-staging.md` runs there. If its Set up once steps have not run, `scripts/staging.sh` refuses (a missing or readable backup folder): report it to the operator.
3. **Bring the checkout up to date.** Run the how-to's step 4, `git switch main && git pull --ff-only`, so the script and compose file that run are `main`'s. Expect `Already up to date` or `Fast-forward`. On a refusal, the checkout has local changes or commits: report it and wait for the operator.
4. **Deploy, on the go-ahead.** The how-to's step 5 has a `**Stop:**` line: the deploy replaces all of Staging's data with the backup and starts the app. Ask the operator for the go-ahead for this step, quoting that line, and wait for it. Then run `scripts/staging.sh deploy <ref>`, adding `--backup bphs-<UTC timestamp>.sqlite` for any backup but the newest nightly one. A rehearsal never uses `--keep-data`: that is for a change with no new migration since the last deploy (`docs/how-to/run-staging.md`, Deploy on the data already there).
5. **Read the deploy's output.** Expect the backup pulled, the build, `0 sessions left (<n> deleted)`, the start-up line `Build <version>+<commit> · <n> migrations, … · maintenance webhook off` naming the ref's short commit, then `staging is healthy`. For an upgrade that adds migrations, the line says `1 applied now` or more (`docs/how-to/upgrade-production.md` step 7). On any failure, stop: the old version is still serving production on its own database. Keep the output and the backup name, and report them.
6. **Check what is running.** Run `scripts/staging.sh status`. Expect the commit, the backup it pulled, `healthy`, and the start-up line from step 5.
7. **Have the pages checked.** The how-to's step 7 opens https://homelab.tailcc2bae.ts.net from a tailnet device with a production account. Ask the operator to open the pages the change touches and say what they showed. Expect the amber strip naming the build.
8. **Write the result block** as the last thing in the reply:

   ```text
   Staging rehearsal: green | red
   Commit: <short commit> (<ref>)
   Backup: bphs-<UTC timestamp>.sqlite
   Start-up line: <the line from step 5, verbatim>
   Pages: <what the operator checked and saw, or "not checked">
   ```

   Green needs all of: `staging is healthy`, a start-up line naming that commit, and the operator's word that the pages work. Anything else is red, with the output that failed under the block.

If homelab is down, the fallback rehearsal is `docs/how-to/restore-to-scratch.md` on the VPS, after the new image is built (`docs/how-to/upgrade-production.md` step 7). Its steps 2 and 3 carry `**Stop:**` lines, so each waits for the operator's go-ahead too. The result block then starts `Scratch rehearsal:`, and its `Start-up line` says whether step 3 listed the accounts (every migration passed) or named the migration that failed.

Not established in bphs-connect: how an agent reaches homelab (the how-to's commands run in a shell there), whether an agent may open Staging's pages itself, or a record of past rehearsals beyond the reply.

**Reply:** each command run with the key lines of its output, each `**Stop:**` step with the go-ahead it got, what was not checked, then the result block.

Sources: docs/how-to/run-staging.md, docs/how-to/upgrade-production.md, docs/how-to/restore-to-scratch.md, docs/directives/production-safety.md, docs/adr/0002-production-copy-as-staging.md, docs/references/production.md, scripts/staging.sh
