---
name: babysit-pr
description: Use to watch an open GitHub PR on a timer and deal with what review bots post on it, for example "babysit PR 42", "watch my PR for Copilot comments", or "stop babysitting PR 42". Not for opening a PR, a one-off review (code-review), a pre-merge swarm (premerge-swarm-review), cloud routines (schedule), general /loop jobs, or merging.
---

# Babysit PR

**Goal:** while a PR is open, check it every 30 or 60 minutes. When a check finds new feedback from bot accounts (Copilot, claude[bot], CodeRabbit and the like), a fresh agent judges every point, fixes the ones it agrees with, pushes, replies, and resolves the thread. Comments from people, including the user's own account, are out of scope: the user chose bots only, so strangers can't steer code changes.

**Never merge, approve, enable auto-merge or force-push.** Merging is the user's call.

`<skill dir>` is the base directory shown when this skill loads, and `<script>` is `python3 <skill dir>/scripts/babysit.py`. `<pr>` is the PR's URL (`gh pr view <number> --json url --jq .url` turns a number into it). Pass the URL to every command, because given a bare number, gh guesses the repo from the git remotes.

CronCreate, CronList, CronDelete and AskUserQuestion may be deferred tools. Load them with ToolSearch (`select:CronCreate,CronList,CronDelete,AskUserQuestion`) before deciding they're missing.

## Start

1. Find the PR: the user's link or number, else the current branch's (`gh pr view --json url --jq .url`).
2. Ask how often with AskUserQuestion, **every time, even if the user already said**: "Every 30 minutes" or "Every hour" (put the one they named first). The user wants to confirm before anything is set up. If they answer *Other*, do what it says (another interval, or cancel).
3. From a clone of the PR's repo, run `<script> start <pr> --worktree <scratchpad>/babysit-pr-<number>`, leaving out `--worktree` if the session has no scratchpad directory. It checks the PR is open, works out where fixes can be pushed, and makes a worktree for fixes, so the user's checkout is never touched. The scratchpad lets the fixer edit files there without permission prompts. If `warnings` isn't empty, show them and ask before continuing.
4. If CronList already has a job whose prompt starts `babysit-pr tick for <pr>`, ask whether to replace it; two jobs on one PR double every reply. Then CronCreate, recurring: pick a minute M from 1–29, and use `M,M+30 * * * *` for 30 minutes or `M * * * *` for hourly, with the tick prompt below filled in.
5. Tell the user the next run time (from CronCreate's result), that ticks run only while this session is open and idle, that the job expires after 7 days, and how to stop it. If this session asks permission before Bash commands, every tick and fix waits for their approval: offer to allow `Bash(python3 <skill dir>/scripts/babysit.py:*)` with the update-config skill. Then run the first tick now.

### Tick prompt

```
babysit-pr tick for <pr>. <script> is python3 <skill dir>/scripts/babysit.py.
1. Run `<script> list <pr>`. If it fails, tell the user the error; if the previous tick failed the same way, say only "still failing".
2. If `state` isn't OPEN: CronDelete this job (CronList finds it), run `<script> stop <pr>`, and tell the user babysitting ended and why, passing on anything `stop` refused to remove. Done.
3. If `busy` is true, the last fixer is still working. Skip this tick.
4. If `blocked` is set, say "PR #<number> blocked: <blocked>" unless the previous tick already said it. Done.
5. If `items` is empty: say "PR #<number>: nothing new" in one line, plus any failing_checks. Done.
6. Mark items that plainly ask for nothing (deploy previews, coverage reports, overviews with no open issues) with `<script> seen <pr> <ids>`.
7. For the rest, run `<script> claim <pr>`, then spawn one general-purpose agent (not fork) in the background: "Read <skill dir>/references/fixer.md and follow it. PR: <pr>. Script: python3 <skill dir>/scripts/babysit.py. Items: <ids>." When it reports, pass its report on to the user.
```

## Stop

When the user asks, or the PR is merged or closed: CronDelete the job (CronList finds it), then `<script> stop <pr>`. That removes the worktree, but refuses while a fixer is working or the worktree holds unpushed work: tell the user what it lists, and add `--force` only once they agree. The record of handled items stays in `~/.cache/babysit-pr/`, so babysitting the PR again later doesn't redo them.

## When it can't finish cleanly

- **gh missing or signed out:** ask the user to install it (`brew install gh` on macOS) or run `! gh auth login`.
- **`start` fails:** its message says why (PR not open, not a clone of that repo, worktree path taken) and what to do.
- **No CronCreate even after ToolSearch** (outside Claude Code): say timed checks need Claude Code, and offer to run one tick now.
- **Blocked** (uncommitted changes in the worktree, a rebase conflict, a refused push): the script records it, and ticks stop sending fixers until the PR head changes. Once the user has fixed the cause, re-run `<script> start <pr> --worktree <same path>`, which clears it.

## Gotchas

- Fix pushes usually trigger a fresh bot review, so expect new items on the next tick.
- After each push, the user's local copy of the branch is behind. Tell them to pull before they push their own work, or their push is rejected.
