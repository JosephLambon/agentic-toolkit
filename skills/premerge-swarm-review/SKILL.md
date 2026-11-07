---
name: premerge-swarm-review
description: Use for a final multi-agent pass on an existing GitHub PR just before merging. Trigger on "premerge swarm review", "swarm review PR 42", "final pass before I merge", "throw the agents at this PR", "stress-test this PR before merging". Not for opening a PR, a static code review of a PR or diff (code-review), a security-only review (security-review), fixing existing review comments, or merging.
---

# Pre-merge swarm review

**Goal:** the last adversarial pass on a PR that's nearly ready to merge. Four reviewers (feature, bugs, performance, security), each in its own fresh context, attack it from one angle at runtime and write a report, which you post on the PR. Every finding has a WHAT, a WHY and a CONFIDENCE level. Fresh contexts are the point: yours is full of reasons the code is fine.

**Never merge, approve or enable auto-merge,** and reviewers never edit, commit or push. Merging is the user's call.

`<skill dir>` is the base directory shown when this skill loads. `<out>` is a new folder in the session scratchpad (or from `mktemp -d`), outside the repo.

## Steps

The order matters: everyone reviews the same pinned commit, and security runs only after the other three have finished and their reports are sound.

1. **Pin the commit.** Only pushed commits are reviewed, so if the local branch is ahead of the PR or has uncommitted changes, tell the user first. From a clone of the PR's repo (`gh repo clone <owner/repo> <out>/repo` if the current folder isn't one), run:
   ```bash
   python3 <skill dir>/scripts/prepare.py <PR url> --out <out>
   ```
   Pass the URL (or a number plus `--repo <owner/repo>`): in a fork's clone, a bare number can resolve to the fork's own PR. The script checks the PR is open, fetches its head, and creates detached worktrees `wt-feature`, `wt-bugs`, `wt-performance` and `wt-security` at the head, and `wt-base` at the merge base. One worktree each, because agents installing, building and serving in one folder break each other's runs. It prints JSON with the SHAs, paths, `visibility`, `push` and `warnings`. If `warnings` isn't empty, show them and ask the user before continuing. A fork PR is the serious one: the reviewers will run a stranger's install scripts and tests on this machine, with the user's credentials.

2. **Launch feature, bugs and performance together.** In one message, spawn three `general-purpose` agents with the prompt below. Don't use `fork`, which inherits this context. Ports: feature 4100–4109, bugs 4110–4119, performance 4120–4139 (it runs head and base). When all three have finished, read the *Report* section of `<skill dir>/references/briefing.md`, then their reports. If one is malformed, or has a verdict its findings contradict (for example *Ready* with a blocker), ask that agent to correct it with SendMessage. Spawn a replacement only if the agent died or wrote no report. If that fails too, its pass didn't complete: say so in a short PR comment in step 4.

3. **Then security.** Spawn one more `general-purpose` agent with role `security` and ports 4140–4149. It goes last so it can treat the others' crashes, odd states and slow paths as leads for attack vectors. Check its report the same way.

4. **Check, then post.**
   - Re-check `gh pr view <PR url> --json headRefOid`. If the head moved, ask the user whether to post the reports as they are (each names the SHA it reviewed) or re-run on the new head.
   - Remove any secrets, tokens, personal data, environment values, local absolute paths and usernames copied from logs. Notification emails send the full text straight away, so nothing posted can be withdrawn.
   - **If `visibility` isn't `PRIVATE` and any report describes an exploitable vulnerability** (usually security's, but a bug catcher's crash can be a denial of service), ask the user before posting it. Offer a redacted comment (counts and severities only), with the details in chat and a draft advisory from the repo's *Security* tab. A public comment hands an unpatched exploit to everyone.
   - Check each report's tables: a `|` or line break inside a cell breaks the table on GitHub.
   - Post each report as its own comment, in the order feature, bugs, performance, security: `gh pr comment <PR url> --body-file <out>/reports/<role>.md`. Don't soften or drop findings. The reports' independence is the point, and validation comes next.

5. **Validate, then offer fixes.**
   - Reproduce every blocker and major, and any minor that's cheap to check, because reviewers over-flag. Mark each one *confirmed*, *rejected* (with the reason) or *unverified*.
   - In chat, give each agent's verdict and comment URL, then list the findings by id (F1, B2, P1, S3…) with severity and validation status.
   - Ask which to fix with AskUserQuestion: "All confirmed blockers and majors", "All confirmed", "None", plus *Other* for picking ids. Ask in chat if the tool isn't available.
   - Fix in a fresh worktree (`git worktree add --detach <out>/wt-fix <head>`): fix each at the root with a regression test, run the full suite, and push with `git push <push.remote or push.url> HEAD:<push.branch>`. If the push is rejected because the head moved, fetch it, rebase onto it, re-run the suite and push again. Never force-push. If `push` is null (a fork that doesn't allow maintainer edits), save the fixes to `<out>/fix.patch` and give the user that.
   - In chat, list by finding id the fix commit or why it was rejected. Offer to post that list as a follow-up PR comment; post it only if the user agrees.
   - Offer to re-run the agents whose findings were fixed, since fixes can add new problems. Run step 6 on the old `<out>` first, then start again at step 1 with a new `<out>`, because the old worktrees are pinned to the reviewed SHA. Launch only those roles, still with security last, and give security the old reports' paths for roles you didn't re-run.

   End by saying whether the PR is ready for the user to merge and, if not, what blocks it.

6. **Clean up.** Run `python3 <skill dir>/scripts/prepare.py --cleanup --out <out>`. It stops every process running inside `<out>` and removes the worktrees. Deal with anything it lists under `failed`, and stop any Docker Compose project or other service a report says it left running.

## Agent prompt

Each agent reads `references/briefing.md` (shared rules and the report format) and its role brief: `references/feature.md`, `references/bugs.md`, `references/performance.md` or `references/security.md`. Apart from the *Report* section (step 2), you don't need to read them. Fill in the angle brackets and drop the lines for other roles.

```
You are the <role> reviewer in a pre-merge swarm review of PR #<n> in <owner/repo>, <PR url>. You didn't write this code: assume it has problems and find them.
Read <skill dir>/references/briefing.md, then <skill dir>/references/<role>.md, and follow both.
PR head <head sha>; base <base branch>, merge base <merge base sha>. Your code: <out>/wt-<role>, detached at the head. Your ports: <range>.
Performance only: the baseline is <out>/wt-base.
Security only: the other reviewers' reports, as leads to verify rather than conclusions: <out>/reports/feature.md, bugs.md and performance.md.
Write your report to <out>/reports/<role>.md. Reply with only its verdict line.
```

## When it can't finish cleanly

- **No subagent tool** (for example in claude.ai): say the review needs independent agents. Offer to run the four passes yourself, in order, with each comment labelled as not independent.
- **`gh` is missing:** ask the user to install it (`brew install gh` on macOS). **Signed out:** ask them to run `! gh auth login`.
- **`prepare.py` fails:** its message says why (not open, not a clone of that repo, head moved during setup, paths already exist) and what to do.
- **The project can't run here** (missing secrets, services or hardware): the reviewers say what they couldn't test under *Not covered* and lower their confidence. Pass that on to the user rather than calling the PR ready.

## Gotchas

- GitHub rejects comments over 65,536 characters. The briefing caps reports below that. If one still goes over, split it into numbered parts and tell the user it's now more than one comment.
- Without a URL, gh picks a repo from the git remotes, which isn't always the PR's (for example in a fork's clone). Address every `gh pr` command by the PR's URL.
