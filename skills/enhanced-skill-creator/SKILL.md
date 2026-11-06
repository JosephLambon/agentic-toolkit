---
name: enhanced-skill-creator
description: Use to create, improve or review any Claude skill or SKILL.md, for example "make a skill for…", "turn this into a skill", "improve this skill" or "review this skill against best practices". Prefer it over plain skill-creator for these, since it wraps skill-creator and adds an adversarial review. Not for evals, benchmarks or description tuning alone (use skill-creator), plugins or hooks, or running an existing skill.
---

# Enhanced skill creator

**Goal:** a skill that triggers when it should, survives a hostile review against Anthropic's skill-building lessons, and uses as few tokens as it can without losing behaviour.

**Placeholders:**
- `<this skill>` is this skill's folder.
- `<target>` is the skill being built.
- `<skill-creator dir>` is the base directory shown when skill-creator loads. If it hasn't loaded, run `find -L ~/.claude/skills -path '*skill-creator/scripts/quick_validate.py'`.

## Workflow

The order matters: review only what's finished, and fix only what the review found.

1. **Create or improve it with skill-creator.** Invoke `anthropic-skills:skill-creator` (or `skill-creator`) and follow it: interview, draft, then evals if the user wants them. If it isn't installed, draft directly. Install scope (personal or project) is the user's call, so ask if it's unclear. Apply *Token efficiency* while drafting. Skip this step when the user only wants a review.
2. **Adversarial review.** Spawn a `general-purpose` subagent with the prompt below. Don't use `fork`, which inherits this context: fresh eyes are the point, because the drafting context is full of reasons the draft is fine. Its pasted `measure.py` output is the "before". With no subagents (for example in claude.ai), follow the prompt yourself in a separate pass and argue against every choice.
3. **Triage and fix** (see *Triage*). Re-review only if the fixes restructured the skill (new or rewritten sections). Line-level fixes don't need it. Pass the rejected findings so they aren't raised again, and stop after two rounds.
4. **Verify.**
   - Run `python3 <skill-creator dir>/scripts/quick_validate.py <target>`. Fix and re-run until it passes, except for the Claude Code-only keys in *Gotchas*.
   - Run `python3 <this skill>/scripts/measure.py <target>` to get the "after".
   - Trigger check (Claude Code only). This is one short billed run, and a miss is a hint, not a verdict. Run it from a folder where the target loads: the repo root for a project skill, or anywhere for a personal skill linked into `~/.claude/skills` (install it first). Use `claude -p "<realistic request>" --max-turns 2 --output-format stream-json --verbose | grep -o '"name":"Skill","input":{[^}]*}'`. On a miss, revise the description and retry once. Then offer skill-creator's description optimiser, or list it under *Still open*.
   - If skill-creator evals exist and behaviour changed, offer to re-run them. Don't start them unasked, because they're billed.
5. **Report** (format below).

## Reviewer prompt

Fill in the angle brackets. Pass paths, not contents, so the checklist loads only into the reviewer's context.

```
Adversarial review. You did not write the skill at <target>; assume it has problems and find them. Do not edit any files.
Read every file in it except evals/, __pycache__ and hidden files, then <this skill>/references/review-checklist.md. Run: python3 <this skill>/scripts/measure.py <target>
To check commands the skill relies on, open only the files it names (for example <skill-creator dir>/scripts/quick_validate.py), not whole folders.
The user requires: <their explicit requirements, one per line, including install scope>. Flag where the skill fails these; never flag them as problems.
<Round 2 only: Already triaged, don't re-raise: <rejected findings and reasons>>
Check every checklist rule, plus anything that would make an agent using the skill misfire, fail, waste tokens, or act on a wrong fact.
Reply with findings only, most severe first, one line each:
<high|med|low> <rule id> <file:line> <problem>. Fix: <concrete change>.
Then paste measure.py's output. No praise, no summary, nothing about rules that passed.
```

## Triage

Reviewers told to find problems will over-flag. Reject a finding, with a one-line reason, when it:
- removes or weakens something the user explicitly asked for
- misreads the skill
- adds machinery the skill doesn't need (config, memory, hooks or scripts) only because the article mentions it
- saves tokens by cutting a *why* that changes behaviour

Accept the rest, even when they're inconvenient.

## Token efficiency

While drafting and while fixing:
- **Description:** it's in every session's skill list, so give triggers only, as short as triggering allows.
- **Body:** it loads on every trigger, so every line must change behaviour. Cut what Claude does by default.
- **Splitting:** conditional material goes to `references/` with a when-to-read line. Material needed on every run stays inline: moving it out (say, a report template into `assets/`) adds a read and saves nothing.
- **Scripts:** deterministic work goes in scripts, whose source never loads unless read.

## Gotchas

- **The review is the expensive step.** One round cost about 98k subagent tokens when this skill was built. That's why the reviewer opens only the files the skill names, and why a second round needs a structural change to justify it.
- **skill-creator says to make descriptions "pushy".** Do that with trigger phrases and near-miss exclusions, within *Token efficiency*, not with a summary of the workflow.
- **Re-fetching the article costs a full fetch** (about 20k subagent tokens when measured). `references/review-checklist.md` is a dated distillation of it. Re-read the article only when the user asks for a refresh, then update the checklist and its date.
- **`quick_validate.py` rejects** angle brackets in the description, descriptions over 1,024 characters, and any frontmatter key other than `name`, `description`, `license`, `allowed-tools`, `metadata` and `compatibility`. A failure on a Claude Code-only key (`hooks`, `model`, `argument-hint` or `disable-model-invocation`) is expected for a Claude Code-only skill. Keep the key, and note it in the report.
- **A colon followed by a space inside an unquoted YAML description** breaks the frontmatter. Rephrase it, or quote the whole value.
- **`measure.py` warnings are hints.** A file that's named only inside a script, or a path that belongs to another skill, can trip them. Check before "fixing" anything.

## Report

Keep it short: the review table, then the size change.

```markdown
## Review (<n> rounds)
| Sev | Rule | Finding | Action |
|---|---|---|---|
| high | D1 | <finding> | Fixed: <change> |
| low | T2 | <finding> | Rejected: <reason> |

## Size
Description <a> → <b> chars. SKILL.md body <a> → <b> words. References <a> → <b> words.

## Still open
<anything unresolved, or None>
```

If step 1 ran, skill-creator's own results (evals and feedback) come first.
