#!/usr/bin/env node
// Compare before/after PNG screenshots pixel by pixel. Node only, no packages.
//
//   node imgdiff.mjs <before.png|before-dir> <after.png|after-dir> [--out DIR] [--threshold N]
//
// Directories are paired by file name (top level only); files on one side only are listed.
// A pixel counts as changed when any RGBA channel differs by more than --threshold
// (default 8, which ignores most rendering noise; 0 = exact).
// For each changed pair it prints the changed pixel count, the bounding box and any size change.
// When only the height changed (a full-page shot that grew or shrank), rows are matched from the
// top and from the bottom, and it reports the band in "after" between them: content outside the
// band is unchanged, so a regression below an inserted section still shows.
// With --out it writes DIR/<name>-diff.png: changes red over a faded copy of "after".
// Exit 0 when the comparison ran (changed or not), 2 on bad input.
import fs from 'node:fs';
import path from 'node:path';
import { decode, encodeRGB } from './png.mjs';

function fail(msg) {
  console.error(`imgdiff: ${msg}`);
  process.exit(2);
}

function load(file) {
  try { return decode(file); } catch (e) { return fail(e.message); }
}

function compare(beforeFile, afterFile, threshold, outDir) {
  const a = load(beforeFile), b = load(afterFile);
  const differs = (i, j) =>
    Math.abs(a.rgba[i] - b.rgba[j]) > threshold || Math.abs(a.rgba[i + 1] - b.rgba[j + 1]) > threshold ||
    Math.abs(a.rgba[i + 2] - b.rgba[j + 2]) > threshold || Math.abs(a.rgba[i + 3] - b.rgba[j + 3]) > threshold;
  const mask = new Uint8Array(b.w * b.h);
  const name = path.basename(afterFile);
  const parts = [];
  let changed = 0, x0 = Infinity, y0 = Infinity, x1 = -1, y1 = -1;
  const mark = (x, y) => {
    changed++; mask[y * b.w + x] = 1;
    if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
  };

  if (a.w === b.w && a.h !== b.h) {
    // A row with only a few stray pixels still lines up (rendering noise would otherwise end the
    // match early); those pixels are marked and counted, never hidden.
    const noise = Math.max(3, Math.ceil(a.w * 0.002));
    const rowDiff = (ya, yb, markIt) => {
      let n = 0;
      for (let x = 0; x < a.w; x++) {
        if (differs((ya * a.w + x) * 4, (yb * b.w + x) * 4)) { n++; if (markIt) mark(x, yb); }
      }
      return n;
    };
    const min = Math.min(a.h, b.h);
    let top = 0, bottom = 0;
    while (top < min && rowDiff(top, top) <= noise) top++;
    while (bottom < min - top && rowDiff(a.h - 1 - bottom, b.h - 1 - bottom) <= noise) bottom++;
    for (let y = 0; y < top; y++) rowDiff(y, y, true);
    for (let k = 0; k < bottom; k++) rowDiff(a.h - 1 - k, b.h - 1 - k, true);
    const stray = changed, bandEnd = b.h - bottom - 1;
    for (let y = top; y <= bandEnd; y++) for (let x = 0; x < b.w; x++) mark(x, y);
    parts.push(`size ${a.w}x${a.h} -> ${b.w}x${b.h}`);
    parts.push(bandEnd >= top
      ? `changed band y ${top}-${bandEnd} of after (rows above line up from the top, ${bottom} rows below from the bottom)`
      : `rows removed at y ${top} of before`);
    parts.push(stray ? `${stray} stray px differ outside it (look: noise or a small regression)` : 'nothing differs outside it');
  } else {
    const ow = Math.min(a.w, b.w), oh = Math.min(a.h, b.h);
    for (let y = 0; y < oh; y++) for (let x = 0; x < ow; x++) if (differs((y * a.w + x) * 4, (y * b.w + x) * 4)) mark(x, y);
    if (!changed && a.w === b.w) return { same: true, line: `same     ${name} (${b.w}x${b.h})` };
    if (changed) {
      const pct = (100 * changed) / (ow * oh);
      parts.push(`${changed} px (${pct < 0.01 ? '<0.01' : pct.toFixed(2)}%)`, `box x ${x0}-${x1}, y ${y0}-${y1}`);
    }
    if (a.w !== b.w || a.h !== b.h) parts.push(`size ${a.w}x${a.h} -> ${b.w}x${b.h}`);
    for (let y = 0; y < b.h; y++) for (let x = 0; x < b.w; x++) if (x >= ow || y >= oh) mask[y * b.w + x] = 1;
  }

  if (outDir) {
    fs.mkdirSync(outDir, { recursive: true });
    const rgb = Buffer.alloc(b.w * b.h * 3);
    for (let p = 0; p < b.w * b.h; p++) {
      const s = p * 4, d = p * 3;
      const grey = (b.rgba[s] * 0.3 + b.rgba[s + 1] * 0.59 + b.rgba[s + 2] * 0.11) * 0.3 + 255 * 0.7;
      if (mask[p]) { rgb[d] = 255; rgb[d + 1] = Math.round(grey * 0.3); rgb[d + 2] = Math.round(grey * 0.3); }
      else rgb.fill(Math.round(grey), d, d + 3);
    }
    const out = path.join(outDir, `${path.parse(name).name}-diff.png`);
    fs.writeFileSync(out, encodeRGB(b.w, b.h, rgb));
    parts.push(`diff ${out}`);
  }
  return { same: false, line: `CHANGED  ${name}: ${parts.join(', ')}` };
}

const args = process.argv.slice(2);
let threshold = 8, outDir = null;
const paths = [];
for (let i = 0; i < args.length; i++) {
  const value = () => (i + 1 < args.length ? args[++i] : fail(`${args[i]} needs a value`));
  if (args[i] === '--threshold') threshold = Number(value());
  else if (args[i] === '--out') outDir = value();
  else if (args[i].startsWith('--')) fail(`unknown option ${args[i]}`);
  else paths.push(args[i]);
}
if (paths.length !== 2 || !Number.isFinite(threshold) || threshold < 0) {
  fail('usage: imgdiff.mjs <before.png|dir> <after.png|dir> [--out DIR] [--threshold N]');
}
const [before, after] = paths;
for (const p of paths) if (!fs.existsSync(p)) fail(`${p} does not exist`);
const isDir = (p) => fs.statSync(p).isDirectory();
if (isDir(before) !== isDir(after)) fail('give two files or two directories');

if (!isDir(before)) {
  console.log(compare(before, after, threshold, outDir).line);
} else {
  const list = (d) => new Set(fs.readdirSync(d).filter((f) => f.toLowerCase().endsWith('.png')));
  const b = list(before), a = list(after);
  let same = 0, changed = 0;
  for (const f of [...b].filter((f) => a.has(f)).sort()) {
    const r = compare(path.join(before, f), path.join(after, f), threshold, outDir);
    console.log(r.line);
    r.same ? same++ : changed++;
  }
  const onlyB = [...b].filter((f) => !a.has(f)).sort(), onlyA = [...a].filter((f) => !b.has(f)).sort();
  for (const f of onlyB) console.log(`only before: ${f}`);
  for (const f of onlyA) console.log(`only after: ${f}`);
  console.log(`${same + changed} pairs: ${same} same, ${changed} changed; ${onlyB.length} only before, ${onlyA.length} only after`);
}
