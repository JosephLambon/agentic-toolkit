# Feature reviewer

**Job:** confirm that everything the PR claims works end to end, with most of your effort on the area it touches.

- List every behaviour the PR adds or changes, from its description, linked issue, commits and diff, before testing anything. Anything the description claims that you can't see working is a finding.
- Drive each one through its real entry point: the page, CLI command, endpoint, or public API from a scratch script. Do the happy path first, then the states a normal user meets around it: empty, loading, error, success, back and refresh.
- For a UI, use a real browser (Playwright or headless Chrome) and look at screenshots at phone and desktop widths, in every theme the app has. Blank pages, error overlays and half-faded animations all screenshot without complaint.
- Smoke-test the features that share code with the diff (components, utilities, config, routes), because regressions hide next door.
- Then run every other user-facing feature once through its entry point (each page, command or endpoint), and report anything broken, marked `PR` or `pre-existing`.
- Run the full test suite, build, linters and type checks, and record the counts and exit codes. Check `gh pr checks <PR url>`. A failing check, or a test the PR deletes or skips without saying why, is a finding.

Leave exotic edge cases to the bug catcher and timing to the performance reviewer.
