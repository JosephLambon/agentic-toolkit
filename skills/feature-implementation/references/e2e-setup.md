# Adding end-to-end tests to a web app that has none

Read this only when the feature is visible in a browser and the repo has no e2e framework yet. Prefer the stack's native option where one exists: Rails system tests, Django with `pytest-playwright`, or Phoenix with Wallaby. Otherwise use Playwright, and keep the set-up minimal.

## Playwright (JS/TS)

- Install it non-interactively: `npm i -D @playwright/test`, then `npx playwright install chromium`. `npm init playwright@latest` prompts for input and will hang.
- Use Chromium only. Add more browsers only if the project asks for them.
- In `playwright.config`, set `testDir` (for example `e2e/`), `use.baseURL`, and a `webServer` block that starts the app and waits on its URL. For a static site, serve the folder (for example `npx http-server -p 4173 .`) rather than loading `file://` URLs.
- Turn the feature flag on through `webServer.env`, or per test (a query parameter, cookie or config route) if the app supports it. If the server reads the flag at start-up, a flag-off e2e test needs a second server or project. Usually it's cheaper to prove flag-off at unit or integration level instead.
- Add a script such as `"test:e2e": "playwright test"`, and make sure the repo's main test command, or CI, runs it.
- Exclude the e2e folder from the unit runner. Vitest and Jest will otherwise pick up Playwright's `*.spec.ts` files and fail.
- Gitignore `test-results/`, `playwright-report/` and `blob-report/`.

## Writing the test

- Select elements by role, label or text (`getByRole('button', { name: 'Save' })`), not by CSS classes.
- Assert with web-first assertions (`await expect(locator).toBeVisible()`), never fixed sleeps.
- One test per user journey through the feature. Leave validation detail to unit tests.

If the browser download is blocked (no network, or a sandbox), that's a blocker to report, not a reason to skip the test.
