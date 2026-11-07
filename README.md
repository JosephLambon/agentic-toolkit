# agentic-toolkit

General-purpose skills for Claude Code, shared across every project on this machine.

## Install

```bash
git clone https://github.com/JosephLambon/agentic-toolkit.git ~/agentic-toolkit
~/agentic-toolkit/install.sh
```

`install.sh` symlinks each folder in `skills/` into `~/.claude/skills/`, where Claude Code picks up personal skills in every session. Because they're links, a `git pull` (or any edit here) takes effect in the next session with no reinstall. Re-run the script after adding a new skill. It never overwrites an existing skill of the same name.

## Skills

| Skill | What it does |
|---|---|
| [`feature-implementation`](skills/feature-implementation/SKILL.md) | How to build any feature: behind a feature flag, test-first (unit, plus integration for APIs, plus end-to-end for web apps), lean tests aiming for 100% line coverage, and a fully green suite before finishing, with any fixed pre-existing failures called out. |
| [`evidenced-pull-request`](skills/evidenced-pull-request/SKILL.md) | Opens every pull request with proof. It confirms the target branch with you, reviews the outgoing diff at a risk-based effort and fixes what it finds, then gathers runtime evidence: tests, end-to-end runs, screenshots from phone to wide-desktop widths (attached with `gh --attach`, which needs gh 2.103.0+), a pixel-level before/after regression check, and confidence scores for security, correctness, quality and feature delivery. It never merges. Its scripts need Node.js; screenshots use Playwright with your installed Chrome. |
| [`enhanced-skill-creator`](skills/enhanced-skill-creator/SKILL.md) | Creates or improves a skill with Anthropic's `skill-creator`, then runs an adversarial review in a fresh subagent against Anthropic's skill-building lessons, and fixes what it finds with token efficiency in mind. Its `scripts/measure.py` shows what each part of a skill costs in context. |
| [`premerge-swarm-review`](skills/premerge-swarm-review/SKILL.md) | A final pass on an open GitHub PR before you merge it. Four agents, each in a fresh context, test it at runtime: a feature reviewer, a QA-style bug catcher and a performance reviewer (base vs head) run in parallel, then a security guard runs last using their reports as leads. Each posts its own PR comment, with a WHAT, WHY and CONFIDENCE for every finding. Fixes happen only after you choose them; it never merges. `scripts/prepare.py` pins the PR head and makes one git worktree per reviewer. |

## Adding a skill

Use `enhanced-skill-creator`, or by hand:

1. Create `skills/<skill-name>/SKILL.md` with `name` and `description` frontmatter. The folder name and `name` must match, in kebab-case.
2. Run `./install.sh`.
3. Start a new Claude Code session and check the skill is listed.

## Tests

The tests use only the Python standard library and git (the `evidenced-pull-request` script tests also need Node.js, and are skipped without it):

```bash
python3 -m unittest discover -s tests
```
