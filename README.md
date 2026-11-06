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
| [`enhanced-skill-creator`](skills/enhanced-skill-creator/SKILL.md) | Creates or improves a skill with Anthropic's `skill-creator`, then runs an adversarial review in a fresh subagent against Anthropic's skill-building lessons, and fixes what it finds with token efficiency in mind. Its `scripts/measure.py` shows what each part of a skill costs in context. |

## Adding a skill

Use `enhanced-skill-creator`, or by hand:

1. Create `skills/<skill-name>/SKILL.md` with `name` and `description` frontmatter. The folder name and `name` must match, in kebab-case.
2. Run `./install.sh`.
3. Start a new Claude Code session and check the skill is listed.

## Tests

The tests use only the Python standard library:

```bash
python3 -m unittest discover -s tests
```
