---
name: feature-implementation
description: Use when implementing a new feature or enhancement in any repo ("add", "build", "implement", "support for", a new endpoint, page, component, option, command or integration), even if the user never mentions tests, TDD or feature flags, and even for small features. Covers flags, test-first, lean tests, a fully green suite and the final report. Not for questions, plans without code, or docs-only edits.
---

# Feature implementation

**Goal:** the feature works, can be switched off, is proven by tests that each earn their place, and the whole suite is green, with anything the developer didn't ask for called out. Where CLAUDE.md, AGENTS.md or CONTRIBUTING deliberately differ, follow the project and say so in the report.

## Constraints

**Baseline first.** Run the full suite before changing anything and note each failure. Without this, you can't prove later which failures you inherited. If the repo has no tests, add its language's standard runner.

**Flag it.** New behaviour goes behind an on/off flag, default off unless the developer says otherwise.
- Use the repo's flag system if it has one. If not, add the smallest thing that works: a flag read from config or an env var. No new vendor or dependency without asking.
- Check it in one or two places at the edges (route, component, command entry), so removing it later is a tiny diff.
- Test both states. The flag-off test proves the old behaviour is intact; without it, the flag is no safety net.
- Skip the flag for bug fixes, pure refactors, dependency or security updates, tooling, docs, migrations (flag the code that uses the new schema instead) and additive library APIs. Give the reason in the report.

**Test first.** Watch each new test fail for the right reason (a failing assertion, not an import error) before writing the code that passes it. The levels add up:
- **Leaf** (isolated logic, no I/O): rich unit tests covering boundaries, invalid input and error paths. Parametrise rather than repeat.
- **Integration or API** (database, network, files, queues, other services, or an exposed endpoint): plus integration tests across the real boundary.
- **Web app** (the feature is visible in a browser): plus an end-to-end test that drives the page through the feature and asserts what the user sees. If there's no e2e framework, read `references/e2e-setup.md`.

**Every test earns its place.** Ask: *what real bug or requirement regression would this catch that the existing tests don't?* If there's no answer, don't write it. Aim for 100% line coverage of new and changed code. Each uncovered line is a missing test, dead code to delete, or untestable glue to name in the report. Prune your own tests before finishing, but don't delete existing ones unasked.

**Finish green.** Run the entire suite, every level. Fix every failure at its root cause, including ones that were failing before you started. A test asserting an outdated requirement may be updated; say why. If a failure can't be fixed here (missing credentials, a paid service, hardware, a product decision), you're not done: say so at the top of the report.

## Gotchas

- "Unrelated, it was failing before" is not a way out. Fix it and report it.
- Faking green counts as failing: skips, `xfail`, a stray `.only`, loosened assertions, inflated timeouts, expected values edited to match wrong output, or mocking out the code under test.
- Running only the tests you touched, then reporting "all tests pass".
- Re-running a flaky test until it passes. Flaky means failing; fix the cause (ordering, shared state, time, network).
- Integration tests that mock the boundary they exist to prove, such as a mocked repository instead of a test database, or a mocked handler instead of a request through the router.
- A flag read once at import or start-up can't be toggled by tests, and its state leaks between them. Read it at call time, or reset it per test. Set the flag explicitly in every test rather than relying on the default, so flipping the default later doesn't silently change what the tests cover.
- Whole-repo coverage percentages hide uncovered new lines. Check the files and lines you changed.
- Bloat that catches nothing: assertion-free tests that only run lines, tests of mocks, framework behaviour, getters or constants, tests pinned to private implementation details, and unit-level rules re-tested end to end.
- Skipping e2e because no browser tooling is installed. Install it.

## Report

End with this report, and keep the headings even when you're being brief. Pre-existing fixes go first, because they're changes the developer didn't ask for.

```markdown
## ⚠ Pre-existing failures I fixed (not part of the request)
- `<test id>`: <cause>. Fixed in `<file:line>` by <change>. <Code bug | Test was wrong, because …>
(Or: None. The suite was green at the start.)

## What I built
<one to three lines>

## Feature flag
`<name>` in `<file>`, checked at `<file:line>`. Default: off. Turn on: <how>. Remove: <what to delete>.
(Or: No flag, because <reason>.)

## Tests added
Unit <n>, integration <n>, e2e <n> in `<files>`, protecting <what>. Coverage of new and changed lines: <x>%. Uncovered: <lines and why, or none>.

## Full suite
`<command(s)>`: <n> passed, 0 failed.
```

If anything still fails, put `## ✗ Not finished: failing tests` above everything else, listing each failure, what you tried and what's needed.
