# Native client tools

Use only tools actually exposed by the current host; these are tool names, not terminal commands. Keep the shared bot-only, confirmation, worktree and no-merge rules unchanged.

## GitHub Copilot CLI

- Ask with `ask_user`. Launch a fresh `general-purpose` agent with `task`; use background mode for the fixer, and `write_agent` for same-task follow-up.
- Use `manage_schedule`: `action: "list"` to inspect jobs, `action: "create"` with the filled tick `prompt` and `interval: "30m"` or `"1h"`, and `action: "stop"` with the returned `id` to cancel. A user-selected alternative interval replaces these examples. Do not use `wakeup`, which belongs to an already-running self-paced loop.
- Schedules belong to the current session, not a cloud service. Report the lifecycle the host actually exposes; do not promise Claude Code's seven-day expiry or invent a next-run timestamp.
- Shell tools and permissions may differ between installations. Use the exposed shell, quote absolute paths, and use `python` if `python3` is unavailable. Do not write Claude `Bash(...)` rules into Copilot settings or blanket-allow tools.

## Claude Code

- Use `AskUserQuestion`, a fresh `general-purpose` Agent/Task, and `SendMessage` when exposed.
- Discover `CronCreate`, `CronList`, `CronDelete` and `AskUserQuestion` with ToolSearch if deferred. For 30 minutes, choose a minute M from 1-29 and use `M,M+30 * * * *`; for hourly use `M * * * *`. List existing jobs before creating one, and delete by returned ID.
- Tell the user ticks require the session to remain open and idle and expire after seven days. If Bash permission prompts block unattended ticks, offer a narrowly scoped `Bash(python3 <skill dir>/scripts/babysit.py:*)` permission through the host's available configuration mechanism; never assume another skill is installed.

If no independent subagent is available, explain that automatic fixes need one; offer to inspect pending feedback without making fixes. If a native scheduler is unavailable after discovery, offer one manual tick rather than claiming a watch is active.
