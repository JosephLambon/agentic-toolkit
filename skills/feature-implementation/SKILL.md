---
name: feature-implementation
description: Standard working method for implementing any new feature or enhancement in any repository. Put the new behaviour behind an easy on/off feature flag, build it test-first (TDD) at the right levels (rich unit tests for isolated leaf changes, plus integration tests for integrations and APIs, plus end-to-end browser tests for web apps), keep tests lean and meaningful while aiming for 100% line coverage, and finish only when the whole test suite passes, highlighting any already-failing tests that were fixed. Use this skill whenever you are about to write code that adds or extends behaviour (a new feature, endpoint, page, component, option, CLI command, integration or user-facing change), even if the user never mentions tests, TDD, coverage or feature flags, and even when the feature seems small. Not for answering questions, planning without code, or docs-only edits.
---

# Feature implementation

Four habits for every feature, in any repo:

1. **Flag it.** New behaviour ships behind a switch that turns it on or off without a code change.
2. **Test first.** TDD, at the right levels: unit tests for leaf changes, plus integration tests for integrations and APIs, plus end-to-end tests for web apps.
3. **Test ruthlessly.** Every test protects real behaviour. Aim for 100% line coverage without bloat.
4. **Finish green.** The whole suite passes before you stop, including tests that were already failing. Call out any of those you fixed.

Why these four: a flag makes a release reversible in seconds instead of a revert and redeploy. A test you watched fail first is proof it can catch the bug it claims to. A lean suite stays fast and trusted, so people keep running it. And a green suite is the only honest meaning of "done": once "red, but only the old failures" is normal, nobody notices the next real break.

**Project instructions come first.** Read CLAUDE.md, AGENTS.md or CONTRIBUTING, and look at how the repo already does flags, tests and coverage. Use its tools, layout and commands. Where the project deliberately rules something out (for example "no feature flags here"), follow the project and say so in the report. These habits fill gaps; they don't override a deliberate local decision.

## Workflow

1. **Baseline.** Before changing anything, run the full test suite and note every failure (test id and a one-line reason). This is the only reliable way to tell, at the end, which failures you inherited and which you caused, and the report needs that list. If the suite can't run at all (missing dependencies, broken config), getting it running is the first job. If the repo has no tests, add the standard runner for its language (pytest, Vitest or Jest, `go test`, `node --test`…) and say so.
2. **Plan.** List the feature's requirements. For each one, decide which test level proves it (see *Test levels*) and where the flag check goes.
3. **Red.** Write the tests for the next requirement. Run them and watch them fail *for the right reason*: an assertion about missing behaviour, not an import error or a typo. A test you never saw fail might not test anything.
4. **Green.** Write the simplest code that makes them pass.
5. **Refactor** with the tests green. Repeat steps 3–5 for each requirement.
6. **Prune** the tests you wrote (see *Ruthless tests*).
7. **Full run.** Run the whole suite and the coverage report. Fix every failure (see *Finish green*).
8. **Report**, using the template at the end.

If you need to explore first (an unfamiliar API, a quick spike), go ahead. Then write the tests before the production version of the code, and check they fail without it.

## Feature flags

Wherever it's possible, put new behaviour behind a flag, so the developer can switch it on or off without changing code.

- **Reuse the repo's flag system.** Search before inventing one: `feature flag`, `featureFlag`, `isEnabled`, `flags.`, `FEATURE_`, `LaunchDarkly`, `Unleash`, `GrowthBook`, `OpenFeature`, `Flipper`, `waffle`. If one exists, use it exactly the way other features do.
- **If there's none, add the smallest thing that works:** one flags module (or config section) that reads each flag from config or an environment variable, with a typed default. Don't add a vendor, service or dependency without asking.
- **Check the flag at the edges**, in as few places as possible: where the route is registered, where the component renders, where the command or job starts. One or two checks keep the flag easy to reason about and make the eventual clean-up a tiny diff. Checks scattered through the code do the opposite.
- **Default it to off** unless the developer says otherwise, so merging is safe. Make it obvious how to turn it on locally.
- **Name it for what it enables**, such as `bulk_export_enabled` or `ENABLE_INVOICE_PDF`. Avoid negatives like `disable_old_export`.
- **Test both states.** Flag on: the new behaviour (your main tests). Flag off: the old behaviour is untouched, usually shown by one focused test at the cheapest level that can show it. The off path is the safety net; if it's broken, the flag is worthless.

**When a flag doesn't fit**, skip it and give the reason in the report. Typical cases: bug fixes, refactors with no change in behaviour, dependency or security updates, build, CI and tooling changes, docs, database migrations (flag the code that uses the new schema, not the migration), and additive library APIs, where calling the new function is already the opt-in.

## Test levels

The levels add up: a web feature backed by a new API endpoint gets all three.

| The change | Tests it needs |
|---|---|
| **Leaf:** an isolated function, class or module with no I/O | Rich unit tests |
| **Integration or API:** talks to a database, the network, the file system, a queue or another service, or exposes an endpoint | Unit tests for the logic, **plus** integration tests across the real boundary |
| **Web application:** the feature shows up in a browser | Whatever the rows above require, **plus** an end-to-end test of the page |

**Rich unit tests** cover the behaviour space: normal cases, boundaries (empty, zero, one, the maximum, off-by-one), invalid input and error paths. Rich means *wide*, not *many*: one parametrised or table-driven test can cover a dozen inputs.

**Integration tests** cross the real boundary: a real HTTP request through the router to the response; a real database (a test container, SQLite or a test schema), not a mocked repository; external services through a local stub server or recorded fixtures. Don't mock the very thing the integration test exists to prove.

**End-to-end tests** load the page in a real browser, do what a user would do with the new feature (click, type, submit), then assert on what the user sees. Use the repo's framework (Playwright, Cypress, WebdriverIO, Selenium…). If it has none, add Playwright with a minimal set-up and say so in the report. One or two journeys through the feature is usually right; leave the detailed rules to the unit tests.

## Ruthless tests

Ask this of every test, before you write it and again when you prune:

> **What real bug, or regression of a requirement, would this test catch that the existing tests wouldn't?**

If there's no clear answer, don't write it, or delete it. Pruning applies to the tests you add. Don't delete existing tests unless asked; if you spot redundant ones, mention them in the report.

Worth writing:
- One test per requirement or acceptance criterion, named for the behaviour (`rejects_expired_codes`, not `test_apply_2`).
- Boundaries and error paths, because that's where bugs live.
- A regression test for each bug you find along the way.
- The flag-off test.

Not worth writing:
- Tests of the language, framework or libraries (a dataclass stores its fields; React renders a prop).
- Trivial getters, setters, constants and pass-throughs with no logic.
- Tests that assert what a mock was told to return.
- Tests pinned to implementation details (private methods, call counts, internal structure) when the behaviour can be observed from outside. They break on every refactor and catch nothing.
- The same behaviour tested again at a higher level without adding anything. An end-to-end test proves the journey and the wiring; it doesn't need to repeat every validation case the unit tests already cover.
- Near-duplicates. Merge them into one parametrised test.
- Large snapshots that nobody reads when they change.

**Coverage: aim for 100% of lines in new and changed code**, measured with the repo's coverage tool or the runner's built-in option (`pytest --cov`, `vitest --coverage`, `jest --coverage`, `go test -cover`, `node --test --experimental-test-coverage`). Treat coverage as a map of untested behaviour, never as a score to game. Every uncovered line is one of three things: behaviour that deserves a real test (write it), dead code (delete it), or glue that genuinely can't be tested sensibly (leave it, and name it in the report). Never write a test that runs lines without asserting anything.

## Finish green

Before you stop, run the **entire** suite, every level, the way CI would. Not just the tests you touched.

- **Fix every failure, including ones that were failing before you started.** "It was already broken" is how suites rot.
- **Fix the cause, not the symptom.** Never reach green by deleting or skipping tests, marking them `xfail`, `.skip` or `@Disabled`, loosening assertions, inflating timeouts, or changing expected values to match wrong output. If a test is genuinely wrong (it asserts a requirement that has since changed), updating it is a legitimate fix; explain why in the report.
- **Flaky tests count as failures.** Re-run to reproduce, then fix the cause (ordering, shared state, time, races, network).
- **If a failure truly can't be fixed here** (it needs credentials, a paid service or hardware you don't have, or the fix needs a product decision), the work isn't finished. Say so at the very top of the report, with what you tried and what's needed. Don't present it as done.

## Report

End with this report, and keep the headings even when you're being brief. The pre-existing failures section goes first, because those are changes the developer didn't ask for and must not miss.

```markdown
## ⚠ Pre-existing failures I fixed (not part of the request)
- `<test id>` was failing before I started: <cause>. Fixed in `<file:line>` by <change>. <Code bug | The test was wrong, because …>
(Or: None. The suite was green before I started.)

## What I built
<one to three lines>

## Feature flag
`<name>`, defined in `<file>`, checked in `<file:line>`. Default: off. To turn on: <how>. To remove later: <what to delete>.
(Or: No flag, because <reason>.)

## Tests added
- Unit: <n> in `<file>`, protecting <what>
- Integration: <n> in `<file>`, protecting <what>
- End-to-end: <n> in `<file>`, protecting <what>
- Coverage of new and changed lines: <x>%. Uncovered: <lines and why, or none>.

## Full suite
`<command>`: <n> passed, 0 failed.
```

If anything is still failing that you couldn't fix, put a `## ✗ Not finished: failing tests` section above everything else, listing each failure, what you tried and what's needed.
