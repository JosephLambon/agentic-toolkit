# Driving states and recording video

Use when `shoot.mjs` can't reach what needs proving: a state behind a click, form input or hover (error messages, open menus, filled forms), or motion a still can't show (an interaction, animation, drag or multi-step flow).

1. Keep the script and its packages outside the repo, so nothing lands beside tracked files. Use the project's Playwright if it has one (point `require` at it); otherwise, in a scratch folder:
   ```bash
   npm init -y >/dev/null && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm i playwright@1.64.1
   npx playwright install ffmpeg     # video only: recording fails without Playwright's own ffmpeg
   npx playwright install chromium   # only if Google Chrome isn't installed (then drop `channel`)
   ```
2. Save as `record.cjs` (CommonJS, so `require` resolves in that folder), set `EVIDENCE`, replace the steps, and run `node record.cjs`:
   ```js
   const { chromium } = require('playwright');
   const SKILL = '<skill dir>';                            // this skill's base directory
   const EVIDENCE = '/absolute/evidence/dir/shots/after';  // never a relative path: it would resolve in the repo
   const WIDTHS = [375, 768, 1280, 1920];
   const SCHEMES = ['light'];                              // ['light', 'dark'] if the app has themes
   const VIDEO = '1280-light';                             // the one run to record; null for stills only

   (async () => {
     const { writeTiles } = await import(`${SKILL}/scripts/png.mjs`);
     const browser = await chromium.launch({ channel: 'chrome' });
     for (const width of WIDTHS) for (const scheme of SCHEMES) {
       const run = `${width}-${scheme}`, size = { width, height: 900 };
       const video = run === VIDEO ? { recordVideo: { dir: `${EVIDENCE}/raw`, size } } : {};
       const context = await browser.newContext({ viewport: size, colorScheme: scheme, ...video });
       const page = await context.newPage();
       await page.goto('http://localhost:3000/feature');
       await page.waitForTimeout(800);                    // pause after each step so a viewer can follow
       await page.getByRole('button', { name: 'Save' }).click();
       await page.getByText('Saved').waitFor();           // assert what the user should see: a broken flow fails the run
       const still = `${EVIDENCE}/saved-${run}.png`;
       await page.screenshot({ path: still, fullPage: true });
       writeTiles(still, `${EVIDENCE}/tiles`, 900);       // Read these: tall images are shrunk past legibility
       const recording = page.video();
       await context.close();                             // a video is only complete after this
       if (recording) await recording.saveAs(`${EVIDENCE}/walkthrough-${run}.webm`);
     }
     await browser.close();
   })();
   ```
   Run the same script against the target's worktree with `EVIDENCE` set to `shots/before` for the regression check.
3. You can't watch the video, so Read the stills' tiles instead. In the PR body, put `![Walkthrough](./shots/after/walkthrough-1280-light.webm)` alone on its own line: GitHub renders a player only there, and in a table it becomes a link.
