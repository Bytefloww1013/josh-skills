### Visual parity

**You own visual equivalence. bphs-connect cannot prove it by image diff. Parity here is a judgment made by looking at screenshots, backed by the repo's DOM and console checks.**

Not established in bphs-connect: visual-regression or pixel-diff tooling, a committed baseline image set that a test compares against (the PNGs in `docs/brand-review/` are committed review evidence that no test or script reads), who reviews the screenshots, or Vitest browser mode. Never report "pixel-exact" or "zero diff". Report what was compared and that the judgment was by eye.

1. Learn the styling system before touching it:
   - Tailwind 4 through `@tailwindcss/vite`. Tokens and component styles live in `web/src/styles.css` (theme tokens such as `--color-accent`, a `@layer components`). Its `@source` lines make Tailwind scan `modules/*/web` and `foundation/*/web`; a new tier needs its own line.
   - The app is light only. There are no dark-theme rules.
   - `DESIGN.md` holds the design rules (One Accent, Words Beside Colour, Measured Grey, Mono Means Data, Twelve Pixel Floor). Its `enforced-by` list is empty, so no tool checks them. You do.
   - The repo's `impeccable` skill says to read its `reference/craft-floor.md` before any UI edit. Its design hook runs from `.claude/settings.json`. It checks each UI edit and makes a deeper pass when the session stops (`docs/skills/impeccable.md`).
2. Capture the before state on a fixed setup:
   - `FIXED_NOW=<ISO instant> docs/verify/scratch-server.sh start` serves a seeded API and SPA on port 3388 with a pinned clock, so two runs give the same data. `start` builds the SPA first unless `SKIP_BUILD=1`, so leave it off after code changes; `stop` removes the server's files.
   - `node docs/verify/browser.mjs --out <folder> [--as priya|marcus|rosa] [--width <px>] <address>...` saves a full-page PNG per address, logged in, in headless Chrome on the UTC clock.
   - Cover the widths `design-qa.md` used: 1440, 834, 390 and 320. Save screenshots where git ignores them: `tmp/browser` is `browser.mjs`'s default folder, and `qa-shots/` is where `design-qa.md` kept its own (both are in `.gitignore`).
3. Change one phase at a time. `design-qa.md`'s checklist compares every implementation phase visually before committing it.
4. Capture the after state with the same seed, clock, account, widths and addresses. Put before and after side by side and judge them by looking, at readable size. `design-qa.md` paired "the same route, content, viewport, and auth state" and used a focused comparison image holding source and rendered artwork in one input; the impeccable `SKILL.md` says to verify by looking at the rendered result at the sizes it ships at. Neither names a human reviewer.
5. Run the checks the repo does have:
   - `browser.mjs` already fails an address on a console error, page error, error or not-found page, or a page still loading after 10s.
   - `SKIP_BUILD=1 node docs/verify/routes-smoke.mjs` opens every route as several accounts and fails on errors, error boundaries, not-found or blank main regions.
   - `docs/verify/quick-check.sh` exits 0.
6. In the PR body, list the browser checks you ran, what they showed, and what you did not check, as the PR template asks. Say that parity was judged by eye, with no pixel diff.
7. Run **Opening a PR** (`playbooks/opening-a-pr.md`).

Brand artwork: keep the supplied PNGs in `brand-assets/` unchanged, publish only curated exports from `web/public/`, and bump the icon query version in `web/index.html` after changing artwork.

**Reply:** components changed, the before and after screenshot pairs (routes, widths, account) and that you judged them by eye, the check output, what's left. State that no pixel diff exists in this repo.

Sources: DESIGN.md, design-qa.md, web/src/styles.css, web/index.html, package.json, AGENTS.md, .gitignore, .claude/skills/impeccable/SKILL.md, docs/skills/impeccable.md, docs/verify/scratch-server.sh, docs/verify/fixed-clock.mjs, docs/verify/browser.mjs, docs/verify/routes-smoke.mjs, docs/verify/quick-check.sh, .github/pull_request_template.md, brand-assets/README.md, vitest.config.ts
