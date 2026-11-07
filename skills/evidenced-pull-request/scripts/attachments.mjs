#!/usr/bin/env node
// Run a gh PR command with one --attach for every local image or video the PR body references.
//
//   node attachments.mjs <body.md> -- gh pr create --base <target> --title "<title>" --body-file <body.md>
//   node attachments.mjs <body.md> -- gh pr edit <url> --body-file <body.md>
//   node attachments.mjs <body.md>     check only: list the files that would be attached
//
// Finds ![alt](path) embeds and [text](path) links whose destination isn't a URL (code spans and
// fenced blocks are skipped, as gh skips them) and resolves them from the body file's folder, as
// gh 2.103.0+ does. Arguments go to gh as an array, so no shell splits or mangles paths.
// Runs nothing (exit 2) when a file is missing, empty, not a type gh attaches (png jpg gif webp svg
// mp4 mov webm), over gh's limit (images 10 MiB, videos 100 MiB), or more than 50; when a local
// link points at something else; or when gh is older than 2.103.0.
// After gh succeeds it reads the PR body back and exits 1 if any local reference is left.
// gh stops at its first failed upload; this prints how to recover (a PR may or may not exist).
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const IMAGE = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']);
const VIDEO = new Set(['.mp4', '.mov', '.webm']);
const MIB = 1024 * 1024;
const MIN_GH = [2, 103, 0];

function fail(lines, code = 2) {
  for (const l of [].concat(lines)) console.error(`attachments: ${l}`);
  process.exit(code);
}

// Local destinations of image embeds and links, ignoring code. Returns [{ ref, image }].
function localRefs(markdown) {
  const text = markdown.replace(/```[\s\S]*?```|~~~[\s\S]*?~~~/g, '').replace(/`[^`\n]*`/g, '');
  const refs = [];
  for (const m of text.matchAll(/(!?)\[[^\]]*\]\(\s*(?:<([^>]+)>|([^)\s]+))(?:\s+"[^"]*")?\s*\)/g)) {
    const ref = m[2] ?? m[3];
    if (/^[a-z][a-z0-9+.-]*:/i.test(ref) || ref.startsWith('#')) continue; // a URL or an anchor
    refs.push({ ref, image: m[1] === '!' });
  }
  return refs;
}

const argv = process.argv.slice(2);
const split = argv.indexOf('--');
const [body] = split === -1 ? argv : argv.slice(0, split);
const command = split === -1 ? [] : argv.slice(split + 1);
if (!body || !fs.existsSync(body)) fail('usage: attachments.mjs <body.md> [-- gh pr create|edit ...]');
const dir = path.dirname(path.resolve(body));

const files = new Set(), problems = [];
for (const { ref, image } of localRefs(fs.readFileSync(body, 'utf8'))) {
  let file;
  try { file = path.resolve(dir, decodeURI(ref)); } catch { problems.push(`${ref}: bad percent-encoding`); continue; }
  const ext = path.extname(file).toLowerCase();
  if (!IMAGE.has(ext) && !VIDEO.has(ext)) {
    problems.push(`${ref}: a local ${image ? 'image' : 'link'} gh can't attach (only png, jpg, gif, webp, svg, mp4, mov, webm); use a URL or remove it`);
  } else if (!fs.existsSync(file)) problems.push(`${file}: missing`);
  else {
    const size = fs.statSync(file).size;
    if (size === 0) problems.push(`${file}: empty (a failed capture?)`);
    else if (IMAGE.has(ext) && size > 10 * MIB) problems.push(`${file}: images must be 10 MiB or less`);
    else if (VIDEO.has(ext) && size > 100 * MIB) problems.push(`${file}: videos must be 100 MiB or less`);
    else files.add(file);
  }
}
if (files.size > 50) problems.push(`${files.size} files; gh attaches at most 50 per command, so cut the body to what a reviewer needs`);
if (problems.length) fail(problems);

if (!command.length) {
  for (const f of files) console.log(f);
  console.log(`${files.size} files OK`);
  process.exit(0);
}

const [gh, ...ghArgs] = command;
const version = spawnSync(gh, ['--version'], { encoding: 'utf8' });
const v = (version.stdout || '').match(/gh version (\d+)\.(\d+)\.(\d+)/);
const tooOld = !v || v.slice(1).map(Number).reduce((cmp, n, i) => cmp || Math.sign(n - MIN_GH[i]), 0) < 0;
if (tooOld) {
  fail([
    `${v ? `gh ${v.slice(1).join('.')}` : `${gh} --version gave no version`} is older than 2.103.0. Before 2.99.0 there is no --attach;`,
    'before 2.103.0 body paths resolve from the working directory, so images are appended, not placed.',
    'Ask the user to upgrade gh (for example `brew upgrade gh`). If they decline, the host is GitHub Enterprise',
    "Server, or you can't push to the base repo (including a fork PR into a repo you can't push to), run the gh",
    `command without this script and give the user the evidence folder to drag images from: ${dir}`,
  ]);
}

const attach = [...files].flatMap((f) => ['--attach', f]);
const run = spawnSync(gh, [...ghArgs, ...attach], { stdio: ['inherit', 'pipe', 'inherit'], encoding: 'utf8' });
process.stdout.write(run.stdout || '');
const url = `${run.stdout || ''} ${ghArgs.join(' ')}`.match(/https?:\/\/\S+\/pull\/\d+/)?.[0];

if (run.status !== 0) {
  fail(url ? [
    'gh stopped at its first failed upload; the PR exists with only the files before it. Fix the cause above, then:',
    `  gh pr view ${url} --json body -q .body > ${path.resolve(body)}`,
    `  node ${process.argv[1]} ${path.resolve(body)} -- gh pr edit ${url} --body-file ${path.resolve(body)}`,
    'Only the references that are still local get attached.',
  ] : 'No PR was created. Fix the cause above and re-run the same command.', run.status || 1);
}
if (!url) fail("gh succeeded but printed no PR URL, so the body wasn't checked; run `gh pr view --json body` yourself.", 1);
const live = spawnSync(gh, ['pr', 'view', url, '--json', 'body', '-q', '.body'], { encoding: 'utf8' });
if (live.status !== 0) fail(`couldn't read the PR body back: ${(live.stderr || '').trim()}`, 1);
const left = localRefs(live.stdout).map((r) => r.ref);
if (left.length) fail([`these references are still local paths in ${url}:`, ...left.map((r) => `  ${r}`)], 1);
console.log(`attached ${files.size} files; no local references left in ${url}`);
