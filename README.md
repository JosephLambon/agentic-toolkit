# agentic-toolkit

General-purpose skills for **GitHub Copilot CLI and Claude Code**, available across projects.

## Shared skills, native client tools

`skills/` is the canonical source for both clients. Reporting limits, verification and safety rules are shared, so the Claude Code version cannot drift back to longer PR descriptions or review diaries. Client-specific tool guidance stays with the relevant skill; there are no independently maintained prompt copies.

Copilot CLI loads personal skills from `~/.copilot/skills/` (also `~/.agents/skills/`), **not** personal `~/.claude/skills/`. Claude Code loads personal skills from `~/.claude/skills/`. See the [Copilot skills documentation](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills) and [Claude Code skills documentation](https://code.claude.com/docs/en/skills).

The installers link only this repository's skills. They do not import unrelated personal skills, third-party plugins or company-specific templates.

## Install

Clone this repository, then choose the client from its root.

**Windows (PowerShell):**

```powershell
.\install.ps1 -Client both
```

Directory junctions work without administrator access or Developer Mode.

**Linux/macOS (Bash):**

```bash
./install.sh --client both
```

Use `copilot` or `claude` instead of `both` to install for one client. Both installers default to **Claude only**, preserving the original `install.sh` behavior. `CLAUDE_SKILLS_DIR` and `COPILOT_SKILLS_DIR` override their respective destinations; Copilot also respects `COPILOT_HOME`.

Links point to the same `skills/` folders: edits or `git pull` take effect when the client next reloads them. Start a new session after installing; re-run the installer after adding a skill. Existing directories and links to other sources are skipped, never replaced. Global installations are changed only when you run an installer.

If a skipped entry is an older standalone copy, compare and back it up before manually replacing that specific entry with a link. The installers never discard local customizations.

## Skills

| Skill | What it does |
|---|---|
| [`feature-implementation`](skills/feature-implementation/SKILL.md) | How to build any feature: behind a feature flag, test-first (unit, plus integration for APIs, plus end-to-end for web apps), lean tests aiming for 100% line coverage, and a fully green suite before finishing, with any fixed pre-existing failures called out. |
| [`evidenced-pull-request`](skills/evidenced-pull-request/SKILL.md) | Confirms the target, reviews the outgoing diff, verifies the pinned commit and opens a PR without merging. The description defaults to **250-400 words**, shorter for small changes: why, behavior-level changes, decisive runtime proof and honest confidence. Full checks, captures and regression comparisons stay private; only material risks justify more space. Scripts require Node.js; attachments need gh 2.103.0+ and screenshots use Playwright/Chrome. |
| [`enhanced-skill-creator`](skills/enhanced-skill-creator/SKILL.md) | Creates or improves a skill with Anthropic's `skill-creator`, then runs an adversarial review in a fresh subagent against Anthropic's skill-building lessons, and fixes what it finds with token efficiency in mind. Its `scripts/measure.py` shows what each part of a skill costs in context. |
| [`premerge-swarm-review`](skills/premerge-swarm-review/SKILL.md) | Four independent runtime reviewers: feature, bugs and performance together, then security using their public reports and private handoffs as leads. Comments default to **80-150 words without findings, 200-400 with findings**. Public evidence proves findings only; investigation and passing checks stay private. Fixes require your choice; it never merges. Python prepares isolated worktrees and finds evidence tools in either client's installation. |
| [`babysit-pr`](skills/babysit-pr/SKILL.md) | Watches bot feedback on an open PR at a confirmed interval, using the current client's native session scheduler. A fresh agent judges feedback and fixes agreed points in an isolated worktree; human comments and design choices remain yours. Requires native scheduling and subagents, with an explicit one-tick fallback when unavailable. Never merges or force-pushes. |

## Adding a skill

Use `enhanced-skill-creator`, or by hand:

1. Create `skills/<skill-name>/SKILL.md` with `name` and `description` frontmatter. The folder name and `name` must match, in kebab-case.
2. Keep rules client-neutral; document genuine tool differences inside that skill, without duplicating its reporting or safety contract.
3. Run the installer for the client(s) you use.
4. Start a new session and check the skill is listed (`copilot skill list` in Copilot CLI).

## Tests

The full suite uses Python's standard library, git, Node.js and POSIX executable fixtures. Run it on Linux/macOS:

```bash
python3 -m unittest discover -s tests
```

On native Windows, the inherited GitHub CLI fixture tests' extensionless fake `gh` scripts are not executable: they can fall through to the real authenticated CLI. Do not use that full-suite command there. Run the native installer, evidence-discovery, image and capture-planning regressions instead:

```powershell
python -m unittest discover -s tests -k Installer -k EvidenceTools -k ImgDiffTest -k ShootTest -k MeasureTest
```

Installer tests use isolated temporary destinations, never your global skill folders. No model-based skill evaluations are run by these deterministic tests.

The Windows capture regression uses npm offline with an isolated cache; it needs the standard Node.js installation with bundled npm, not a browser or network.
