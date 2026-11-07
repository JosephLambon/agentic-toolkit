#!/usr/bin/env node
// Run a gh PR command with one --attach for every local image or video the PR body references.
//
//   node attachments.mjs <body.md> -- gh pr create --base <target> --title "<title>" --body-file <body.md>
//   node attachments.mjs <body.md> -- gh pr edit <url> --body-file <body.md>
//   node attachments.mjs <body.md> -- gh pr comment <url> --body-file <body.md>
//   node attachments.mjs <body.md>     check only: list the files that would be attached
//
// Finds ![alt](path) embeds and [text](path) links whose destination isn't a URL (code spans and
// fenced blocks are skipped, as gh skips them; alt text may hold one level of [brackets]) and
// resolves them from the body file's folder, as gh 2.103.0+ does. Refuses local src paths in HTML
// <img>, <video> and <source> tags, which gh doesn't rewrite. Arguments go to gh as an array, so no shell splits or mangles paths.
// Runs nothing (exit 2) when a file is missing, empty, not a type gh attaches (png jpg gif webp svg
// mp4 mov webm), over gh's limit (images 10 MiB, videos 100 MiB), or more than 50; when a local
// link points at something else; or when gh is older than 2.103.0.
// After gh succeeds it reads the PR body (or, for `gh pr comment`, the new comment) back and exits 1
// if any local reference is left.
// gh stops at its first failed upload; this prints how to recover (a PR or comment may or may not
// exist). After a comment is posted, the recovery is always --edit-last, never a second comment.
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

const isUrlOrAnchor = (ref) => /^[a-z][a-z0-9+.-]*:/i.test(ref) || ref.startsWith('#');
const withoutCode = (markdown) => markdown.replace(/```[\s\S]*?```|~~~[\s\S]*?~~~/g, '').replace(/`[^`\n]*`/g, '');

// Local destinations of image embeds and links, ignoring code. Returns [{ ref, image }].
function localRefs(markdown) {
  const refs = [];
  const link = /(!?)\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*(?:<([^>]+)>|([^)\s]+))(?:\s+"[^"]*")?\s*\)/g;
  for (const m of withoutCode(markdown).matchAll(link)) {
    const ref = m[2] ?? m[3];
    if (!isUrlOrAnchor(ref)) refs.push({ ref, image: m[1] === '!' });
  }
  return refs;
}

// Local src paths in HTML media tags, ignoring code. gh never rewrites these.
function localHtmlSrcs(markdown) {
  const tag = /<(?:img|video|source)\b[^>]*?\ssrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/gi;
  return [...withoutCode(markdown).matchAll(tag)].map((m) => m[1] ?? m[2] ?? m[3]).filter((src) => !isUrlOrAnchor(src));
}

const argv = process.argv.slice(2);
const split = argv.indexOf('--');
const [body] = split === -1 ? argv : argv.slice(0, split);
const command = split === -1 ? [] : argv.slice(split + 1);
if (!body || !fs.existsSync(body)) fail('usage: attachments.mjs <body.md> [-- gh pr create|edit|comment ...]');
const dir = path.dirname(path.resolve(body));

const files = new Set(), problems = [];
const source = fs.readFileSync(body, 'utf8');
for (const src of localHtmlSrcs(source)) {
  problems.push(`${src}: a local src in an HTML tag, which gh doesn't upload; use ![alt](${src}) instead`);
}
for (const { ref, image } of localRefs(source)) {
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

function checkLive(live, where, recovery = []) {
  if (live.status !== 0) fail([`couldn't read ${where} back: ${(live.stderr || '').trim()}`, ...recovery], 1);
  const left = [...localRefs(live.stdout).map((r) => r.ref), ...localHtmlSrcs(live.stdout)];
  if (left.length) fail([`these references are still local paths in ${where}:`, ...left.map((r) => `  ${r}`), ...recovery], 1);
  console.log(`attached ${files.size} files; no local references left in ${where}`);
  process.exit(0);
}

if (ghArgs[0] === 'pr' && ghArgs[1] === 'comment') {
  const pr = ghArgs[2] && !ghArgs[2].startsWith('-') ? ghArgs[2] : '<pr>';
  const editLast = [
    `  node ${process.argv[1]} ${path.resolve(body)} -- gh pr comment ${pr} --edit-last --body-file ${path.resolve(body)}`,
    "Don't re-run the original command: it would post a second comment, and every comment notifies subscribers.",
  ];
  if (run.status !== 0) {
    fail([`gh failed (it stops at its first failed upload). Check \`gh pr view ${pr} --comments\`. If a comment was posted, fix the cause and update it with:`,
      ...editLast, 'If none was posted, fix the cause and re-run the same command.'], run.status || 1);
  }
  const m = (run.stdout || '').match(/https?:\/\/([^/\s]+)\/([^/\s]+)\/([^/\s]+)\/pull\/\d+#issuecomment-(\d+)/);
  if (!m) {
    fail([`gh succeeded but printed no comment URL, so the comment wasn't checked. Check it with \`gh pr view ${pr} --comments\`; to change it, use:`,
      ...editLast], 1);
  }
  const [commentUrl, host, owner, repo, id] = m;
  checkLive(spawnSync(gh, ['api', '--hostname', host, `repos/${owner}/${repo}/issues/comments/${id}`, '--jq', '.body'],
    { encoding: 'utf8' }), commentUrl, ['The comment is posted. Fix the cause, then update it with:', ...editLast]);
}

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
checkLive(spawnSync(gh, ['pr', 'view', url, '--json', 'body', '-q', '.body'], { encoding: 'utf8' }), url);
