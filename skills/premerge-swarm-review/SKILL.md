---
name: premerge-swarm-review
description: Use for "premerge swarm review", "swarm review PR 42", "final pass before I merge", "throw the agents at this PR", or "stress-test this PR before merging". Not for opening PRs, static diff reviews, security-only reviews, fixing review comments, or merging.
---

# Pre-merge swarm review

**Goal:** four fresh, independent reviewers (feature, bugs, performance, security) investigate a nearly-ready PR at runtime. Post concise comments describing the functionality examined, accessible findings with decisive proof, and only material unverified risks. Keep complete verification records private; shorten publication, not investigation. Each finding separates the observed problem (WHAT), root cause (WHY), confidence and next step.

**Never merge, approve or enable auto-merge,** and reviewers never edit, commit or push. Merging is the user's call.

`<skill dir>` is the base directory shown when this skill loads. `<out>` is a new folder in the session scratchpad, outside the repo.

Use native tools: `ask_user`, `task` and `write_agent` in Copilot CLI; AskUserQuestion, Agent/Task and SendMessage in Claude Code. Below, those operations mean the current host's tools. Use the exposed shell's quoting and path syntax; `python` can replace `python3`.

## Steps

The order matters: everyone reviews the same pinned commit; security runs only after the other three have finished and their public reports and private handoffs are sound.

1. **Pin the commit.** Only pushed commits are reviewed, so if the local branch is ahead of the PR or has uncommitted changes, tell the user first. From a clone of the PR's repo (`gh repo clone <owner/repo> <out>/repo` if the current folder isn't one), run:
   ```bash
   python3 <skill dir>/scripts/prepare.py <PR url> --out <out>
   ```
   Pass the URL (or a number plus `--repo <owner/repo>`): in a fork's clone, a bare number can resolve to the fork's own PR. The script checks the PR is open, fetches its head, and creates detached worktrees `wt-feature`, `wt-bugs`, `wt-performance` and `wt-security` at the head, and `wt-base` at the merge base. One worktree each, because agents installing, building and serving in one folder break each other's runs. It prints JSON with the SHAs, paths, `visibility`, `push`, `evidence` and `warnings`. `evidence` is the `evidenced-pull-request` skill's folder, whose scripts the reviewers use for screenshots and you use to post; if it's null (that skill or Node is missing), reviewers fall back to Playwright or headless Chrome, and you post with plain gh. If `warnings` isn't empty, show them and ask the user before continuing. A fork PR is the serious one: the reviewers will run a stranger's install scripts and tests on this machine, with the user's credentials.

2. **Launch feature, bugs and performance together.** In one message, spawn three `general-purpose` agents with the prompt below. Don't use `fork`, which inherits this context. Ports: feature 4100-4109, bugs 4110-4119, performance 4120-4139 (it runs head and base). When all three finish, read *Private verification*, *Proof* and *Report* in `<skill dir>/references/briefing.md`, then each report and `<out>/reports/<role>/verification.log`. Enforce that contract:
   - A high-level functionality summary, not a command/setup diary; the default word budgets, with extra space only for distinct material findings or essential proof.
   - Findings with plain-language WHAT, a root-cause WHY (or explicit uncertainty), confidence with a short basis, origin, severity, ID and actionable next step.
   - Only finding-specific proof under Evidence, no passing-case media or tables; only critical PR/role-specific gaps under Not covered.
   - Complete private records at the pinned SHA, with failures and material gaps reflected honestly in the public verdict. No *Ready* with a PR blocker/major or a critical verification gap.
   - Valid tables and available, size-compliant attachments (`node <evidence>/scripts/attachments.mjs <out>/reports/<role>.md` lists them).
   Ask the same agent to correct failures with SendMessage. Spawn a replacement only if it died or wrote no report. If that also fails, post a short incomplete-pass comment in step 4 naming the examined scope, blocking verification and required next check; never call it ready.

3. **Then security.** Spawn one more `general-purpose` agent with role `security` and ports 4140-4149. Give it the other three reports AND private handoffs, including important failures and runtime observations omitted from public comments. These are leads to verify, not conclusions. Check its report and handoff the same way.

4. **Check, then post.**
   - Re-check `gh pr view <PR url> --json headRefOid`. If the head moved, ask the user whether to post the reports as they are (each names the SHA it reviewed) or re-run on the new head.
   - Run `python3 <skill dir>/scripts/prepare.py --scan --out <out>`. It flags local paths, usernames and tokens in reports and per-role `.log` files, including private records. Resolve every hit in public text and cited proof; make sanitized excerpts rather than uploading private originals, and re-render changed log images. It can't detect every kind of personal data or read images: inspect the public text and every planned attachment. Never attach/link private handoffs or raw verification logs. Notification emails send the full text immediately and uploads can't be deleted.
   - **If `visibility` isn't `PRIVATE` and any report describes an exploitable vulnerability** (usually security's, but a bug catcher's crash can be a denial of service), ask the user before posting it. Offer a redacted comment (examined functionality and counts/severities only, no exploit details or evidence files), with details in chat and a draft advisory from the repo's *Security* tab. A public comment hands an unpatched exploit to everyone.
   - Check each report's tables: a `|` or line break inside a cell breaks the table on GitHub.
   - Post each report as its own comment, in the order feature, bugs, performance, security:
     ```bash
     node <evidence>/scripts/attachments.mjs <out>/reports/<role>.md -- \
       gh pr comment <PR url> --body-file <out>/reports/<role>.md
     ```
     It attaches every file the report references, refuses to run if a file or the gh version is wrong, then reads the comment back to check every file landed. Follow its messages when it fails. With `evidence` null, run the `gh pr comment` with one `--attach <file>` per referenced file (gh 2.103.0 or later), then check the comment with `gh pr view <PR url> --comments`.
   - Don't soften or drop findings. The reports' independence is the point, and validation comes next.

5. **Validate, then offer fixes.**
   - Reproduce every blocker and major, and any minor that's cheap to check, because reviewers over-flag. Mark each one *confirmed*, *rejected* (with the reason) or *unverified*.
   - In chat, give one verdict/comment URL per role, then findings by ID (F1, B2, P1, S3) with severity and validation status. Mention material verification gaps and unresolved cleanup requiring action, not commands, passing checks or a second evidence gallery.
   - Ask which to fix with AskUserQuestion: "All confirmed blockers and majors", "All confirmed", "None", plus *Other* for picking ids. Ask in chat if the tool isn't available.
   - Fix in a fresh worktree (`git worktree add --detach <out>/wt-fix <head>`): fix each at the root with a regression test, run the full suite, and push with `git push <push.remote or push.url> HEAD:<push.branch>`. If the push is rejected because the head moved, fetch it, rebase onto it, re-run the suite and push again. Never force-push. If `push` is null (a fork that doesn't allow maintainer edits), save the fixes to `<out>/fix.patch` and give the user that.
   - In chat, list by finding id the fix commit or why it was rejected. Offer to post that list as a follow-up PR comment; post it only if the user agrees.
   - Offer to re-run the agents whose findings were fixed, since fixes can add new problems. Run step 6 on the old `<out>` first, then start again at step 1 with a new `<out>`, because the old worktrees are pinned to the reviewed SHA. Launch only those roles, still with security last, and give security the old reports AND private handoff paths for roles you didn't re-run, labelled with their reviewed SHAs.

   End with whether the PR is ready for the user to merge and, if not, the blocking findings or critical unverified checks and next action.

6. **Clean up.** Run `python3 <skill dir>/scripts/prepare.py --cleanup --out <out>`. It attempts to stop processes under `<out>` and removes worktrees, retaining reports and private evidence. Inspect `stopped` and `failed`; missing `lsof` requires manual process cleanup. Use handoffs to stop residual owned PIDs/services and Docker Compose projects, and verify none remain. Do not stop unrelated processes.

## Agent prompt

Each agent reads `references/briefing.md` (shared rules, private handoff and public format) and its role brief: `references/feature.md`, `references/bugs.md`, `references/performance.md` or `references/security.md`. Apart from the sections named in step 2, you don't need to read them. Fill in the angle brackets and drop the lines for other roles.

```
You are the <role> reviewer in a pre-merge swarm review of PR #<n> in <owner/repo>, <PR url>. You didn't write this code: assume it has problems and find them.
Read <skill dir>/references/briefing.md, then <skill dir>/references/<role>.md, and follow both.
PR head <head sha>; base <base branch>, merge base <merge base sha>. Your code: <out>/wt-<role>, detached at the head. Your ports: <range>.
Evidence folder: <out>/reports/<role>/. Evidence tools: <evidence, or none>.
Performance only: the baseline is <out>/wt-base.
Security only: read <out>/reports/feature.md, <out>/reports/bugs.md and <out>/reports/performance.md AND verification.log in each matching role's evidence folder. Follow local record references for important crashes, odd states, slow paths and failures; verify these leads independently.
Write the concise public report to <out>/reports/<role>.md and the private handoff to <out>/reports/<role>/verification.log. Never link the handoff in the public report. Reply with only the verdict line.
```

## When it can't finish cleanly

- **No subagent tool** (for example in claude.ai): say the review needs independent agents. Offer to run the four passes yourself, in order, with each comment labelled as not independent.
- **`gh` is missing:** ask the user to install it (`brew install gh` on macOS). **Signed out:** ask them to run `! gh auth login`.
- **`prepare.py` fails:** its message says why (not open, not a clone of that repo, head moved during setup, paths already exist) and what to do.
- **The project can't run here** (missing secrets, services or hardware): retain the full failure privately. State the critical PR-specific unverified behaviour and required next check under *Not covered*, lower confidence, and do not call an incomplete critical pass ready.

## Gotchas

- GitHub rejects comments over 65,536 characters. Edit to the briefing's much smaller budgets; split into numbered parts only if genuinely distinct material findings and their essential proof cannot fit. Never split merely to publish a diary.
- Without a URL, gh picks a repo from the git remotes, which isn't always the PR's (for example in a fork's clone). Address every `gh pr` command by the PR's URL.
