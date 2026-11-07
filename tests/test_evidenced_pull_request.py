"""Tests for skills/evidenced-pull-request/scripts (imgdiff.mjs, shoot.mjs).

They need Node.js on PATH. shoot.mjs is only tested where it needs no network
or browser (argument errors and text-page rendering via --dry-run).
"""
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/evidenced-pull-request/scripts"
NODE = shutil.which("node")


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def write_png(path, pixels, filters=(0,), alpha=False):
    """Write an 8-bit RGB(A) PNG. Row y uses filters[y % len(filters)], so a
    test can force every PNG filter type, as real encoders such as Chrome do."""
    h, w = len(pixels), len(pixels[0])
    bpp = 4 if alpha else 3
    raw_rows = [bytes(v for px in row for v in (px if alpha else px[:3])) for row in pixels]
    out, prev = bytearray(), bytes(w * bpp)
    for y, row in enumerate(raw_rows):
        f = filters[y % len(filters)]
        enc = bytearray()
        for i, x in enumerate(row):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            pred = [0, a, b, (a + b) // 2, _paeth(a, b, c)][f]
            enc.append((x - pred) & 0xFF)
        out += bytes([f]) + enc
        prev = row

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6 if alpha else 2, 0, 0, 0)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                           + chunk(b"IDAT", zlib.compress(bytes(out))) + chunk(b"IEND", b""))


def png_size(path):
    data = Path(path).read_bytes()
    return struct.unpack(">II", data[16:24])


def gradient(w=12, h=10):
    return [[((x * 20) % 256, (y * 25) % 256, (x * y * 7) % 256, 255) for x in range(w)] for y in range(h)]


@unittest.skipUnless(NODE, "node is not installed")
class ImgDiffTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def run_diff(self, *args):
        return subprocess.run([NODE, str(SCRIPTS / "imgdiff.mjs"), *map(str, args)],
                              capture_output=True, text=True, timeout=60)

    def test_identical_pixels_match_across_every_filter_type_and_alpha(self):
        img = gradient()
        write_png(self.dir / "a.png", img, filters=(0,))
        write_png(self.dir / "b.png", img, filters=(1, 2, 3, 4), alpha=True)
        result = self.run_diff(self.dir / "a.png", self.dir / "b.png", "--out", self.dir / "d")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("same", result.stdout)
        self.assertNotIn("CHANGED", result.stdout)
        self.assertFalse((self.dir / "d").exists() and any((self.dir / "d").iterdir()))

    def test_changed_pixel_reports_box_percentage_and_writes_diff_image(self):
        before, after = gradient(), gradient()
        after[7][3] = (255, 255, 255, 255)
        write_png(self.dir / "a.png", before, filters=(4, 2))
        write_png(self.dir / "b.png", after, filters=(3, 1))
        result = self.run_diff(self.dir / "a.png", self.dir / "b.png", "--out", self.dir / "d")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CHANGED", result.stdout)
        self.assertIn("x 3-3, y 7-7", result.stdout)
        self.assertIn("1 px (0.83%)", result.stdout)  # 1 of 120 pixels
        diff = self.dir / "d/b-diff.png"
        self.assertTrue(diff.exists())
        self.assertEqual(png_size(diff), (12, 10))

    def test_threshold_ignores_small_colour_shifts(self):
        before, after = gradient(), gradient()
        r, g, b, a = after[2][2]
        after[2][2] = ((r + 5) % 256, g, b, a)
        write_png(self.dir / "a.png", before)
        write_png(self.dir / "b.png", after)
        self.assertIn("same", self.run_diff(self.dir / "a.png", self.dir / "b.png").stdout)
        strict = self.run_diff(self.dir / "a.png", self.dir / "b.png", "--threshold", "0")
        self.assertIn("CHANGED", strict.stdout)

    def test_size_change_is_reported(self):
        write_png(self.dir / "a.png", gradient(12, 10))
        write_png(self.dir / "b.png", gradient(12, 14))
        result = self.run_diff(self.dir / "a.png", self.dir / "b.png", "--out", self.dir / "d")
        self.assertIn("CHANGED", result.stdout)
        self.assertIn("12x10 -> 12x14", result.stdout)
        self.assertEqual(png_size(self.dir / "d/b-diff.png"), (12, 14))

    def test_directories_pair_by_name_and_list_unmatched_files(self):
        (self.dir / "before").mkdir()
        (self.dir / "after").mkdir()
        write_png(self.dir / "before/home.png", gradient())
        write_png(self.dir / "after/home.png", gradient())
        write_png(self.dir / "before/old.png", gradient())
        write_png(self.dir / "after/new.png", gradient())
        result = self.run_diff(self.dir / "before", self.dir / "after")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("only before: old.png", result.stdout)
        self.assertIn("only after: new.png", result.stdout)
        self.assertIn("1 pairs: 1 same, 0 changed; 1 only before, 1 only after", result.stdout)

    def test_inserted_section_is_isolated_as_a_band(self):
        top, inserted, bottom = gradient(12, 6), [[(9, 9, 9, 255)] * 12] * 4, gradient(12, 5)[::-1]
        write_png(self.dir / "a.png", top + bottom)
        write_png(self.dir / "b.png", top + inserted + bottom)
        result = self.run_diff(self.dir / "a.png", self.dir / "b.png")
        self.assertIn("changed band y 6-9 of after", result.stdout)
        self.assertIn("5 rows below from the bottom), nothing differs outside it", result.stdout)

    def test_regression_below_an_inserted_section_widens_the_band(self):
        top, inserted, bottom = gradient(12, 6), [[(9, 9, 9, 255)] * 12] * 4, gradient(12, 5)[::-1]
        broken = [row[:] for row in bottom]
        broken[3] = [(255, 0, 0, 255)] * 12
        write_png(self.dir / "a.png", top + bottom)
        write_png(self.dir / "b.png", top + inserted + broken)
        result = self.run_diff(self.dir / "a.png", self.dir / "b.png")
        self.assertIn("changed band y 6-13 of after", result.stdout)
        self.assertIn("nothing differs outside it", result.stdout)

    def test_stray_pixels_keep_rows_aligned_but_are_reported(self):
        top, inserted, bottom = gradient(12, 6), [[(9, 9, 9, 255)] * 12] * 4, gradient(12, 5)[::-1]
        noisy = [row[:] for row in bottom]
        noisy[3][5] = (255, 0, 0, 255)
        write_png(self.dir / "a.png", top + bottom)
        write_png(self.dir / "b.png", top + inserted + noisy)
        result = self.run_diff(self.dir / "a.png", self.dir / "b.png")
        self.assertIn("changed band y 6-9 of after", result.stdout)
        self.assertIn("1 stray px differ outside it", result.stdout)

    def test_bad_input_exits_2(self):
        (self.dir / "x.png").write_bytes(b"not a png")
        result = self.run_diff(self.dir / "x.png", self.dir / "x.png")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a PNG", result.stderr)

    def test_option_without_value_exits_2(self):
        write_png(self.dir / "a.png", gradient())
        result = self.run_diff(self.dir / "a.png", self.dir / "a.png", "--out")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--out needs a value", result.stderr)

    def test_tall_images_split_into_tiles(self):
        write_png(self.dir / "tall.png", gradient(4, 25))
        script = (f"import {{ writeTiles }} from {str(SCRIPTS / 'png.mjs')!r};"
                  f"console.log(writeTiles({str(self.dir / 'tall.png')!r}, {str(self.dir / 't')!r}, 10).length)")
        result = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "3", result.stderr)
        self.assertEqual(png_size(self.dir / "t/tall.tile-03.png"), (4, 5))


FAKE_GH = """#!/bin/bash
printf '%s|' "$@" >> "$FAKE_GH_LOG"; echo >> "$FAKE_GH_LOG"
case "$1" in
  --version) echo "gh version ${FAKE_GH_VERSION:-2.103.3} (2026-10-26)" ;;
  pr) case "$2" in
        create|edit)
          if [ -n "$FAKE_GH_FAIL" ]; then printf '%s' "$FAKE_GH_FAIL_OUT"; echo "could not upload" >&2; exit 1; fi
          echo "https://github.com/o/r/pull/7" ;;
        view) cat "$FAKE_GH_BODY" ;;
      esac ;;
esac
"""


@unittest.skipUnless(NODE, "node is not installed")
class AttachmentsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name).resolve()
        (self.dir / "shots").mkdir()
        self.gh = self.dir / "gh"
        self.gh.write_text(FAKE_GH)
        self.gh.chmod(0o755)
        self.log = self.dir / "gh.log"
        self.live_body = self.dir / "live.md"
        self.live_body.write_text("![a](https://github.com/user-attachments/assets/1)\n")
        self.env = {"PATH": "/usr/bin:/bin", "FAKE_GH_LOG": str(self.log), "FAKE_GH_BODY": str(self.live_body)}

    def run_attach(self, body, *command, **env):
        (self.dir / "body.md").write_text(body)
        args = [NODE, str(SCRIPTS / "attachments.mjs"), str(self.dir / "body.md")]
        if command:
            args += ["--", str(self.gh), *command]
        return subprocess.run(args, capture_output=True, text=True, timeout=30, env={**self.env, **env})

    def gh_calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_check_only_lists_each_local_file_once(self):
        write_png(self.dir / "shots/a.png", gradient())
        (self.dir / "shots/walk.webm").write_bytes(b"video")
        result = self.run_attach("| ![a 375](./shots/a.png) | [full size](shots/a.png) |\n\n"
                                 "![Walkthrough](./shots/walk.webm)\n\n![badge](https://img.shields.io/x.svg)\n"
                                 "[docs](https://example.com) [top](#why)\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split("\n")[:2], [str(self.dir / "shots/a.png"), str(self.dir / "shots/walk.webm")])

    def test_runs_gh_with_one_attach_per_file_then_checks_the_live_body(self):
        write_png(self.dir / "shots/my shot.png", gradient())
        result = self.run_attach("![a](<./shots/my shot.png>)\n", "pr", "create", "--title", "Two words")
        self.assertEqual(result.returncode, 0, result.stderr)
        create = [c for c in self.gh_calls() if c.startswith("pr|create|")][0]
        self.assertEqual(create, f"pr|create|--title|Two words|--attach|{self.dir / 'shots/my shot.png'}|")
        self.assertIn("pr|view|https://github.com/o/r/pull/7|--json|body|-q|.body|", self.gh_calls())
        self.assertIn("no local references left", result.stdout)

    def test_local_reference_left_in_the_live_body_fails(self):
        write_png(self.dir / "shots/a.png", gradient())
        self.live_body.write_text("![a](./shots/a.png)\n")
        result = self.run_attach("![a](./shots/a.png)\n", "pr", "create")
        self.assertEqual(result.returncode, 1)
        self.assertIn("./shots/a.png", result.stderr)

    def test_old_gh_runs_nothing(self):
        write_png(self.dir / "shots/a.png", gradient())
        result = self.run_attach("![a](./shots/a.png)\n", "pr", "create", FAKE_GH_VERSION="2.99.0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("older than 2.103.0", result.stderr)
        self.assertFalse(any(c.startswith("pr|") for c in self.gh_calls()))

    def test_failed_upload_after_pr_created_prints_the_edit_command(self):
        write_png(self.dir / "shots/a.png", gradient())
        result = self.run_attach("![a](./shots/a.png)\n", "pr", "create",
                                 FAKE_GH_FAIL="1", FAKE_GH_FAIL_OUT="https://github.com/o/r/pull/9\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("gh pr view https://github.com/o/r/pull/9 --json body -q .body >", result.stderr)
        self.assertIn("-- gh pr edit https://github.com/o/r/pull/9 --body-file", result.stderr)

    def test_failed_upload_without_pr_says_none_exists(self):
        write_png(self.dir / "shots/a.png", gradient())
        result = self.run_attach("![a](./shots/a.png)\n", "pr", "create", FAKE_GH_FAIL="1", FAKE_GH_FAIL_OUT="")
        self.assertEqual(result.returncode, 1)
        self.assertIn("No PR was created", result.stderr)

    def test_unattachable_local_link_fails(self):
        (self.dir / "shots/run.log").write_text("ok")
        result = self.run_attach("[log](./shots/run.log)\n", "pr", "create")
        self.assertEqual(result.returncode, 2)
        self.assertIn("run.log", result.stderr)
        self.assertEqual(self.gh_calls(), [])

    def test_missing_empty_and_badly_encoded_files_fail(self):
        (self.dir / "shots/empty.png").write_bytes(b"")
        result = self.run_attach("![x](./shots/missing.png) ![e](./shots/empty.png) ![p](./shots/100%.png)\n")
        self.assertEqual(result.returncode, 2)
        for text in ("missing", "empty", "percent-encoding"):
            self.assertIn(text, result.stderr)

    def test_references_inside_code_are_ignored(self):
        result = self.run_attach("```md\n![x](./nope.png)\n```\nUse `![x](./also-nope.png)`.\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_more_than_fifty_files_fails(self):
        refs = []
        for i in range(51):
            write_png(self.dir / f"shots/{i}.png", gradient(2, 2))
            refs.append(f"![{i}](./shots/{i}.png)")
        result = self.run_attach("\n".join(refs))
        self.assertEqual(result.returncode, 2)
        self.assertIn("at most 50", result.stderr)


@unittest.skipUnless(NODE, "node is not installed")
class ShootTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def run_shoot(self, *args):
        return subprocess.run([NODE, str(SCRIPTS / "shoot.mjs"), *map(str, args)],
                              capture_output=True, text=True, timeout=60)

    def test_missing_out_is_an_error(self):
        result = self.run_shoot("https://example.com")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--out", result.stderr)

    def test_plans_every_width_and_scheme_for_a_url(self):
        result = self.run_shoot("http://localhost:3000/a", "--out", self.dir, "--name", "home",
                                "--widths", "375,1280", "--schemes", "light,dark", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("home-375-light.png", "home-375-dark.png", "home-1280-light.png", "home-1280-dark.png"):
            self.assertIn(name, result.stdout)
        self.assertIn("--full-page", result.stdout)

    def test_text_file_becomes_an_escaped_terminal_page(self):
        log = self.dir / "run.log"
        log.write_text("$ curl /api\n<script>alert(1)</script> & done\n\x1b[32mPASS\x1b[0m\n")
        result = self.run_shoot(log, "--out", self.dir / "shots", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("run-1000-light.png", result.stdout)
        page = next((self.dir / "shots").glob(".run.terminal.html"))
        html = page.read_text()
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; done", html)
        self.assertNotIn("<script>", html)
        self.assertIn("\nPASS\n", html)
        self.assertNotIn("\x1b", html)


if __name__ == "__main__":
    unittest.main()
