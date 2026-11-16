---
name: evidenced-pull-request
description: Use before opening a pull request, including "open a PR", "raise a PR into develop", "create a pull request" or "put this up for review". Not for reviewing, merging, babysitting or commenting on an existing PR.
---

# Evidenced pull request

**Goal:** a short PR description that supports an informed human decision: why the change matters, what it does, decisive runtime proof and honest readiness. Review and verify thoroughly; publish the conclusions, not the investigation.

**Never merge.** Don't run `gh pr merge`, enable auto-merge or push to the target branch, even if asked to "land" or "finish" it. Merging is always a human's call. Stop once the PR is open.

`<skill dir>` below is the base directory shown when this skill loads.

Use native tools: `ask_user`, `task` and `write_agent` in Copilot CLI; AskUserQuestion, Agent/Task and SendMessage in Claude Code. Use the exposed shell's quoting and path syntax; `python` can replace `python3`.

## Steps

The order matters: each step works on the result of the one before.

1. **Confirm the target, every time.** Run `git fetch --prune --all`, list the remote branches, and ask the user (AskUserQuestion where available) which remote branch the PR goes into, offering any branch they named first. Never take it from the default branch, repo docs or an earlier PR without asking: the wrong base means reviewing and proving the wrong diff. With more than one remote, also confirm the base repo and the remote to push to, because gh otherwise picks a remote itself: pass `--repo <owner/repo>` to every `gh pr` command, plus `--head <push owner>:<branch>` on `gh pr create`. If `gh pr list --head <branch> --state open` shows a PR already, stop and ask whether to update that one instead (step 5).
2. **Make the branch match what will merge.** Only pushed commits are in a PR: list any uncommitted files and ask whether they belong in it. If the branch is behind `<remote>/<target>`, update it with the repo's convention (ask if unclear). Once the branch is on the remote, merge the target in rather than rebasing, or ask before `git push --force-with-lease`.
3. **Review and fix.** The diff is `<remote>/<target>...HEAD`. Choose effort by risk, using the highest row that matches:

   | Change | Level |
   |---|---|
   | Docs, comments or config values only | low |
   | Small, isolated logic or UI | medium |
   | A typical feature, or anything touching auth, payments, personal data, migrations, concurrency, a public API, CI, permissions or dependencies | high |
   | Roughly 1,000+ changed lines, or a wide blast radius | xhigh |

   Invoke the `code-review` skill with that level and the diff range. Use max or ultra only if the user asks; they're the costliest. Also run `security-review` when the diff touches auth, input handling, secrets, file or network access, or dependencies. Both can silently fall back to the repo's default branch, so check that each covered the files in `git diff --name-only <remote>/<target>...HEAD`. If one didn't, or isn't installed, give a fresh `general-purpose` subagent the explicit range and ask for one line per finding (severity, file:line, problem). A fresh agent matters because your own context is full of reasons the code is fine. Reviewers over-flag, so validate each finding. Fix the real ones at the root, add a test for each bug, re-run the full suite, and note each finding with its fix or the reason it was rejected. Re-review only if the fixes were substantial.
4. **Gather evidence** (below). Record the fetched base and reviewed HEAD commit IDs locally; prove that committed head. Uncommitted changes must not contaminate the build or evidence. If the base, head or outgoing diff changes, repeat the affected review and verification.
5. **Open the PR.** Fetch the confirmed base again; if it changed, return to steps 2-4. Run `git push -u <remote> HEAD` and confirm the remote head equals the reviewed, evidenced commit. An uncommitted merge tree is not proof of the pushed branch. Write the body to `<evidence dir>/body.md` using the public-output contract and template; include required repo-template sections without duplicating them. Then:
   ```bash
   node <skill dir>/scripts/attachments.mjs <evidence dir>/body.md -- \
     gh pr create --base <target> --title "<title>" --body-file <evidence dir>/body.md
   ```
   For a PR found in step 1, use `-- gh pr edit <url> --body-file <evidence dir>/body.md` instead. The script adds an `--attach` for every local image or video the body references, refuses to run gh if a file or the gh version is wrong, then reads the PR back to check every image landed. Follow its messages when it fails. Verify the PR's base and head still match the confirmed, pinned refs; a mismatch means draft status and renewed review/proof, not readiness. Give the user the URL, target, compact confidence ratings and actionable gaps; say it is ready only when review and proof are complete.

## Gather evidence (keep full records locally)

Evidence is the software running, not a description of the code. Verify each behavioural claim in *What changed*. Complete every step below regardless of how little is published. Keep commands, outputs, review findings and their dispositions, all captures and comparisons in the evidence folder.
- **Checks:** run the full test suite, linters, type checks and the build. Record each command, its exit code and its pass/fail counts.
- **End to end:** run the software and drive the change through its real entry point (page, CLI command, endpoint), including the error and edge states it touches. Use the `run` skill if the project has a launch recipe.
- **Visual, on every PR:** `node <skill dir>/scripts/shoot.mjs <url|file> --out <evidence dir>/shots/after --name <screen>` captures 375, 768, 1280 and 1920 px. Use the project's breakpoints if it has them, and add `--schemes light,dark` if it has themes. It captures pages as they load, so reach other states by URL; for states behind clicks or input, and for interactions, animation or multi-step flows that need a video, read `references/playwright.md`. With no UI (CLI, API, library, infra), save the real command, its output and exit code to a `.log` file and pass that: it becomes an image.
- **Regression check:** run the target in a worktree (`git worktree add <tmp> <remote>/<target>`) with its own install, build and port; the main checkout's server would show the PR's code. Shoot the same screens, plus neighbouring screens the change shouldn't touch, into `shots/before`, then run `node <skill dir>/scripts/imgdiff.mjs <evidence dir>/shots/before <evidence dir>/shots/after --out <evidence dir>/diff`. When a page's height changed, it reports the changed band and any stray pixels outside it. Every change must be explained by the PR; anything else is a regression to fix or call out. On a re-run after fixes, first move `shots/after` to `shots/pass-<n>`, then also diff `pass-<n>` against the new `after` with `--out <evidence dir>/diff/pass-<n>`, so the before→after diffs aren't overwritten. Remove the worktree and stop the servers afterwards.
- **Look at every image** with the native image viewer before using it. For shots taller than 2000 px, inspect the tiles `shoot.mjs` writes to `tiles/`, because the full image gets shrunk past legibility. Blank pages, error overlays, half-faded animations, the wrong theme and stale builds all screenshot without complaint.
- Keep the evidence folder outside the repo (scratchpad or `mktemp -d`), so none of it gets committed.

## Public-output contract

Use plain English for a reader unfamiliar with the code. Default to **250-400 words for the whole body**, shorter for small changes; exceed 400 only for material risks, failures or required repo-template content, not more workings.

- **Why / What changed:** explain the problem, context and behaviour-level change, including important scope boundaries. Avoid a file-by-file implementation tour.
- **Evidence:** publish only core runtime outcomes showing the intended behaviour and a meaningful regression/control check. State the real boundary of the proof: local or simulated checks are not a deployed pipeline or real tenant test.
- Select the minimum decisive attachments, normally one image or a before/after pair; use one short video instead when motion matters. No breakpoint/theme gallery, successful-check inventory or default log/diff images. Keep `body.md` at the evidence root and use existing relative attachment paths.
- Keep command tables, raw timings and pixel counts, setup/cleanup narratives and review transcripts local. Do not attach a full evidence dump as a workaround.
- **Before production:** list only material human checks, such as real dev/test pipeline deployment or tenant integration; omit when none remain. No generic limitations or harmless inherited warnings. Always disclose material failures, uncertainty and incomplete proof with impact and next action, even when that needs more space.

## Confidence

Score four areas from 0 to 100%: **Security**, **Code correctness**, **Quality** (bug-free, no regressions) and **Feature delivery**. Publish one short explanation per score, naming the decisive verification and any material reason it is limited; keep the detailed rationale local.
- 90–100: verified at runtime end to end, covered by tests, review clean, no unverified paths.
- 70–89: verified, with named gaps.
- 50–69: mostly reasoned from the code.
- Below 50: not verified.

Nothing checked only on paper scores above 69. An honest low score helps the reviewer; an inflated one makes the PR dangerous to approve.

## PR body template

```markdown
## Why?
<short problem/context and any issue link>

## What changed
- <plain-language behaviour change and important scope boundary>

## Evidence
- <observed end-to-end result and whether proof was local, simulated or deployed>
- <observed control/regression outcome showing the application still works>

<optional attachment: replace with an existing filename, or remove both lines>
![Selected runtime proof](./shots/after/<screen>-1280-light.png)

## Confidence
| Area | Confidence | Short explanation |
|---|---|---|
| Security | <n>% | <decisive proof / material gap> |
| Code correctness | <n>% | <decisive proof / material gap> |
| Quality | <n>% | <decisive proof / material gap> |
| Feature delivery | <n>% | <decisive proof / material gap> |

## Before production
<only material human checks with concrete next actions; omit this section if none>
```

## When it can't finish cleanly

- On the target or default branch, or a detached HEAD: ask before creating a branch for the work.
- The remote isn't on GitHub (gh can't open the PR): stop and tell the user.
- Tests still fail, or evidence can't be completed here (missing credentials, hardware, a paid service): open the PR with `--draft`, put **Not ready** at the top of Evidence with what fails, its impact and what's needed, and tell the user. Brevity and confidence scores must never hide a blocker or turn incomplete proof into readiness.
- `attachments.mjs` says gh is too old, or gh can't attach (GitHub Enterprise Server, or no write access to the base repo): follow its message, and keep the evidence folder until the user has the images.

## Gotchas

- `git diff <target>` (two dots, or none) also shows the target's newer commits, reversed. Use three dots against a freshly fetched remote ref, not a stale local branch.
- Plain `gh pr edit --attach`, with no body file, appends duplicates and leaves `./shots/` references broken. To change evidence on an open PR, always go through `attachments.mjs` with `gh pr edit <url> --body-file`.
- Uploads are permanent and gh can't delete them. Check every image and log for secrets, tokens, personal data and real customer records first.
- gh allows videos up to 100 MiB, but GitHub's real limit depends on the plan and is lower on free accounts, so keep videos short. A long full-page shot can pass the 10 MiB image limit: diff the full-page shots locally anyway (imgdiff has no limit), and for the body retake both sides with `--viewport-only`, or attach the tiles.
- Two captures of an unchanged page can differ by a few scattered pixels of rendering noise. If a diff is tiny, shoot the before side twice: the same noise there means it isn't a regression.
- `position: fixed` elements (sticky bars, cookie banners, dev-only toolbars) appear once, part-way down a full-page shot, over the content. They look like layout bugs; hide dev-only overlays before shooting, and recognise the rest.
- Entrance and scroll-reveal animations can leave content invisible in a screenshot. Raise `--wait`, or show it in a video.
