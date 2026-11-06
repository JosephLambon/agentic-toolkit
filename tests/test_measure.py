"""Tests for skills/enhanced-skill-creator/scripts/measure.py."""
import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/enhanced-skill-creator/scripts/measure.py"
_spec = importlib.util.spec_from_file_location("measure", SCRIPT)
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)


class MeasureTest(unittest.TestCase):
    def make_skill(self, files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for rel, content in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content)
        return root

    def test_sizes_description_body_and_bundled_files(self):
        root = self.make_skill({
            "SKILL.md": "---\nname: demo\ndescription: Use when demoing.\n---\n"
                        "Read references/guide.md, then copy assets/logo.png.\n",
            "references/guide.md": "one two three four\n",
            "assets/logo.png": b"\x89PNG",
        })
        result = measure.measure(root)
        self.assertEqual(result["description_chars"], len("Use when demoing."))
        self.assertEqual(result["body_words"], 5)
        files = {f["path"]: f for f in result["files"]}
        self.assertEqual(files["references/guide.md"]["words"], 4)
        self.assertEqual(files["assets/logo.png"]["bytes"], 4)
        self.assertIsNone(files["assets/logo.png"]["words"])
        self.assertEqual((result["unmentioned"], result["missing"]), ([], []))

    def test_parses_block_and_quoted_descriptions(self):
        expected = "Use when demoing."
        cases = {
            "folded": ("description: >\n  Use when\n  demoing.\nname: demo", expected),
            "literal": ("description: |\n  Use when\n  demoing.\nname: demo", expected),
            "double-quoted": ('name: demo\ndescription: "Use when demoing."', expected),
            "single-quoted": ("name: demo\ndescription: 'Use when demoing.'", expected),
            "plain-wrapped": ("description: Use when\n  demoing.\nname: demo", expected),
            "quoted-wrapped": ('description: "Use when\n  demoing."\nname: demo', expected),
            "missing": ("name: demo", ""),
        }
        for label, (frontmatter, want) in cases.items():
            with self.subTest(label):
                parsed = measure.parse_description(frontmatter)
                self.assertEqual(parsed.replace("\n", " "), want)

    def test_flags_unmentioned_and_missing_files_but_ignores_evals_and_other_skills(self):
        root = self.make_skill({
            "SKILL.md": "---\nname: demo\ndescription: d\n---\n"
                        "Run `scripts/run.py`. See references/gone.md and data.md.\n"
                        "Validate with <skill-creator dir>/scripts/quick_validate.py.\n",
            "scripts/run.py": "print('hi')\n",
            "references/a.md": "x\n",
            "evals/case/prompt.md": "x\n",
            ".DS_Store": b"\x00",
        })
        result = measure.measure(root)
        # "data.md" in the text must not count as a mention of a.md.
        self.assertEqual(result["unmentioned"], ["references/a.md"])
        self.assertEqual(result["missing"], ["references/gone.md"])
        self.assertEqual(sorted(f["path"] for f in result["files"]),
                         ["references/a.md", "scripts/run.py"])

    def test_cli_prints_compact_report(self):
        root = self.make_skill({
            "SKILL.md": "---\nname: demo\ndescription: Use when demoing.\n---\nBody.\n",
            "references/orphan.md": "x\n",
        })
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = measure.main([str(root)])
        self.assertEqual(code, 0)
        report = out.getvalue()
        self.assertIn("description: 17 chars", report)
        self.assertIn("SKILL.md body: 1 words", report)
        self.assertIn("references/orphan.md is never mentioned in SKILL.md", report)

    def test_cli_fails_without_skill_md(self):
        root = self.make_skill({})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = measure.main([str(root)])
        self.assertEqual(code, 1)
        self.assertIn("SKILL.md", err.getvalue())


if __name__ == "__main__":
    unittest.main()
