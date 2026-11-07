#!/usr/bin/env node
// Screenshot a URL, a local HTML file or a text/log file at several widths and colour schemes.
//
//   node shoot.mjs <url|file> --out DIR [--name NAME] [--widths 375,768,1280,1920]
//                  [--schemes light|dark|light,dark] [--height 900] [--wait 1500]
//                  [--wait-for CSS] [--viewport-only] [--text] [--dry-run]
//
// Writes DIR/<NAME>-<width>-<scheme>.png. NAME defaults to the file's name, or "page" for a URL.
// Full-page by default; --viewport-only captures just the first screen (width x --height).
// A .txt/.log/.out file (or any file with --text) is rendered as a terminal-style page at 1000 px,
// so CLI, API or test output becomes an image. Put the exact command and its exit code in it.
// Runs `npx playwright@$PLAYWRIGHT_VERSION screenshot` (default 1.64.1) with installed Google
// Chrome, so nothing is downloaded but the npm package; without Chrome it falls back to
// Playwright's Chromium (once: `npx playwright@1.64.1 install chromium`). Playwright sets the
// viewport itself, so phone widths work (a plain headless Chrome window can't go below ~500 px).
// Warns when a file is over GitHub's 10 MiB image limit for `gh --attach`. Shots taller than
// 2000 px are also cut into viewport-height tiles in DIR/tiles/ for reading at full size.
// It only captures pages as they load: reach other states by URL, or use references/playwright.md.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { writeTiles } from './png.mjs';

const VERSION = process.env.PLAYWRIGHT_VERSION || '1.64.1';
const MAX_IMAGE = 10 * 1024 * 1024;
const TILE_OVER = 2000; // agents' image viewers shrink taller images until detail is unreadable
const TEXT_EXT = new Set(['.txt', '.log', '.out']);

let tempPage = null;
function fail(msg) {
  if (tempPage && !opts.dryRun) fs.rmSync(tempPage, { force: true });
  console.error(`shoot: ${msg}`);
  process.exit(2);
}

const opts = { widths: null, schemes: null, height: null, wait: 1500, fullPage: true, text: false, dryRun: false };
let target = null;
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  const next = () => (i + 1 < argv.length ? argv[++i] : fail(`${a} needs a value`));
  if (a === '--out') opts.out = next();
  else if (a === '--name') opts.name = next();
  else if (a === '--widths') opts.widths = next().split(',').map(Number);
  else if (a === '--schemes') opts.schemes = next().split(',');
  else if (a === '--height') opts.height = Number(next());
  else if (a === '--wait') opts.wait = Number(next());
  else if (a === '--wait-for') opts.waitFor = next();
  else if (a === '--viewport-only') opts.fullPage = false;
  else if (a === '--text') opts.text = true;
  else if (a === '--dry-run') opts.dryRun = true;
  else if (a.startsWith('--')) fail(`unknown option ${a}`);
  else target = a;
}
if (!target) fail('give a URL or file to capture');
if (!opts.out) fail('--out DIR is required');
if (opts.widths && opts.widths.some((w) => !Number.isInteger(w) || w < 1)) fail('--widths must be whole numbers');
if (opts.schemes && opts.schemes.some((s) => s !== 'light' && s !== 'dark')) fail('--schemes takes light and/or dark');
fs.mkdirSync(opts.out, { recursive: true });

let url;
if (/^(https?|file):/i.test(target)) {
  url = target;
  opts.name ??= 'page';
} else {
  if (!fs.existsSync(target)) fail(`${target} does not exist`);
  const parsed = path.parse(target);
  opts.name ??= parsed.name;
  if (opts.text || TEXT_EXT.has(parsed.ext.toLowerCase())) {
    const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const body = esc(fs.readFileSync(target, 'utf8').replace(/\x1b\[[0-9;?]*[A-Za-z]/g, '')); // drop ANSI colours
    tempPage = path.join(opts.out, `.${parsed.name}.terminal.html`);
    fs.writeFileSync(tempPage, `<!doctype html><meta charset="utf-8"><title>${esc(parsed.base)}</title>
<style>body{margin:0;background:#0d1117;color:#e6edf3;font:14px/1.5 ui-monospace,Menlo,Consolas,monospace}
header{padding:10px 24px;background:#161b22;color:#8b949e;border-bottom:1px solid #30363d}
pre{margin:0;padding:20px 24px;white-space:pre-wrap;overflow-wrap:anywhere}</style>
<header>${esc(parsed.base)}</header><pre>${body}</pre>`);
    url = pathToFileURL(path.resolve(tempPage)).href;
    opts.widths ??= [1000];
    opts.height ??= 100; // full-page capture grows to fit the text, with no empty space below it
  } else {
    url = pathToFileURL(path.resolve(target)).href;
  }
}
opts.widths ??= [375, 768, 1280, 1920];
opts.schemes ??= ['light'];
opts.height ??= 900;
if (!Number.isInteger(opts.height) || opts.height < 1) fail('--height must be a whole number');

const shots = [];
for (const w of opts.widths) {
  for (const s of opts.schemes) shots.push({ w, s, file: path.join(opts.out, `${opts.name}-${w}-${s}.png`) });
}

function args(shot, channel) {
  const a = ['-y', `playwright@${VERSION}`, 'screenshot'];
  if (channel) a.push('--channel', channel);
  a.push('--viewport-size', `${shot.w},${opts.height}`, '--color-scheme', shot.s, '--wait-for-timeout', String(opts.wait));
  if (opts.waitFor) a.push('--wait-for-selector', opts.waitFor);
  if (opts.fullPage) a.push('--full-page');
  a.push(url, shot.file);
  return a;
}

function run(a) {
  return new Promise((resolve) => {
    const child = spawn('npx', a, { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '';
    child.stdout.on('data', (d) => (out += d));
    child.stderr.on('data', (d) => (out += d));
    child.on('close', (code) => resolve({ code, out }));
    child.on('error', (e) => resolve({ code: 1, out: String(e) }));
  });
}

function report(shot) {
  const buf = fs.readFileSync(shot.file);
  const size = buf.length, h = buf.readUInt32BE(20);
  const warn = size > MAX_IMAGE ? '  WARNING: over 10 MiB, gh --attach will refuse it; use --viewport-only' : '';
  console.log(`wrote ${shot.file} (${buf.readUInt32BE(16)}x${h}, ${Math.round(size / 1024)} KB)${warn}`);
  if (h > TILE_OVER) {
    const tiles = writeTiles(shot.file, path.join(opts.out, 'tiles'), Math.max(opts.height, 900));
    console.log(`  read these ${tiles.length} tiles to inspect it: ${path.join(opts.out, 'tiles', path.parse(shot.file).name)}.tile-*.png`);
  }
}

if (opts.dryRun) {
  for (const shot of shots) console.log(`npx ${args(shot, 'chrome').join(' ')}`);
  process.exit(0);
}

// The first shot finds out whether installed Chrome is usable; the rest run four at a time.
let channel = 'chrome';
let first = await run(args(shots[0], channel));
if (first.code && /distribution 'chrome' is not found|chrome.*(not found|not installed)/i.test(first.out)) {
  channel = null;
  first = await run(args(shots[0], channel));
}
if (first.code) {
  if (/Executable doesn't exist|playwright install/i.test(first.out)) {
    console.error(`shoot: no browser. Run once: npx playwright@${VERSION} install chromium`);
  }
  fail(`capture failed for ${shots[0].file}:\n${first.out.trim()}`);
}
report(shots[0]);

let failed = 0;
const queue = shots.slice(1);
await Promise.all(Array.from({ length: Math.min(4, queue.length) }, async () => {
  for (let shot; (shot = queue.shift()); ) {
    const r = await run(args(shot, channel));
    if (r.code) { failed++; console.error(`shoot: capture failed for ${shot.file}:\n${r.out.trim()}`); }
    else report(shot);
  }
}));
if (tempPage) fs.rmSync(tempPage, { force: true });
process.exit(failed ? 1 : 0);
