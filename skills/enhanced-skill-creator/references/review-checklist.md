# Skill review checklist

This checklist is distilled from Thariq Shihipar, "Lessons from building Claude Code: how we use skills", claude.dev, 3 June 2026 (https://claude.dev/blog/lessons-from-building-claude-code-how-we-use-skills/), checked on 6 November 2026. The E rules (token efficiency) are the user's requirement, not the article's. Rule ids are for findings.

The article's tips are options, not a quota. Flag a missing technique only if this skill would actually benefit from it.

## Scope
- **S1 One job.** The skill should fit mainly one of the article's nine types: library/API reference, product verification, data fetching and analysis, business process automation, code scaffolding and templates, code quality and review, CI/CD and deployment, runbooks, or infrastructure operations. "The ones that try to do too much straddle several and confuse the agent."
- **S2 Compose, don't copy.** Reference other skills by name and the model will invoke them if they're installed. Dependencies aren't managed, so say what to do if a needed skill is missing.

## Description
- **D1 Triggers, not a summary.** "The description field is not a summary, it's a description of when to trigger this skill."
- **D2 Real trigger phrases.** Use the words users actually type, for example "Trigger on 'babysit', 'watch CI', 'make sure this lands'".
- **D3 No near-miss over-triggering.** Say what the skill is not for, where a neighbouring skill or a plain request could be mistaken for it.

## Content
- **C1 Don't state the obvious.** "A skill that restates what Claude would do by default adds context without adding value." Keep only what "pushes Claude out of its normal way of thinking."
- **C2 Gotchas.** "The highest-signal content in any skill is the Gotchas section." Build it from failure points Claude actually hits. Flag invented, generic or missing gotchas.
- **C3 No railroading.** "State the goal and the constraints, not every step." Keep a strict order only where order matters, and say why.
- **C4 A way out.** Say what to do when the skill can't finish cleanly (the article's example: "If it can't land cleanly, explain why").
- **C5 Correct.** Commands, paths, flags and facts must be right. Check anything checkable.

## Structure (progressive disclosure)
- **P1 Map the files.** "Tell Claude what files are in your skill, and it will read them at appropriate times." Every bundled file is named in SKILL.md with a when-to-read condition.
- **P2 Split by need.** Conditional or bulky material (API detail, rare paths, long examples) goes in `references/`. Templates Claude copies go in `assets/`. For a branching skill, use a table that maps each situation to its file.
- **P3 Don't over-split.** Material needed on every run stays inline. Moving it out only adds a read.

## Scripts, state and hooks
- **T1 Code over prose.** Put deterministic or repeated work in scripts, so Claude can "spend its turns on composition". Put gotchas in the script's docstrings.
- **T2 Setup.** If the skill needs user-specific values, store them in a `config.json` in the skill directory. When it's missing, ask the user (with AskUserQuestion for multiple choice) and save the answers.
- **T3 Memory.** If each run should build on the last, keep an append-only log, JSON or SQLite file. For plugins, use `${CLAUDE_PLUGIN_DATA}`.
- **T4 On-demand hooks.** Guardrails wanted only while the skill is active (such as blocking `rm -rf`, or blocking edits outside one folder) go in skill hooks, not always-on hooks.

## Token efficiency
- **E1 Description cost.** Every installed skill's description is in every session's skill list. A personal skill costs this in every repo; a project skill only in its own repo. Use the shortest description that still triggers. Install scope is the user's call: report its per-session cost, and never change it.
- **E2 Body cost.** The body loads each time the skill triggers, so every line should change behaviour. Cut preambles, repetition, restated headings and extra examples where one will do. Prefer bullets to prose. Keep the *why* as a short clause where it changes behaviour, and don't cut it to save tokens.
- **E3 Lazy loading.** Script source costs nothing unless read; only its output does. Keep that output compact. Subagent prompts should pass file paths, not contents, and ask for compact replies.
- **E4 Numbers.** Run `scripts/measure.py` and report the before and after figures.
