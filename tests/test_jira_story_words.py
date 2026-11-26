import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "skills" / "jira-user-story"


class JiraStoryWordsTest(unittest.TestCase):
    def setUp(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.description = re.search(r"```markdown\n(.*?)```", skill, re.S)[1]

    def run_check(self, description, title="Correct the notification sender"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "story.md"
            path.write_text(description, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SKILL / "scripts" / "check_words.py"), title, str(path)],
                capture_output=True, text=True, check=False,
            )

    def test_counts_visible_link_labels_not_destinations(self):
        description = self.description.replace(
            "- [Attachment filename or descriptive source link] — [what it shows or why it matters]",
            "- [Sample trace](https://example.test/a_(b)) — shows the old sender.",
        )
        result = self.run_check(description)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("Evidence and references: 6/50", result.stdout)

    def test_rejects_overlong_title_and_scenario_independently_of_total(self):
        description = self.description.replace("**Then**", "**Then** " + "extra " * 45)
        result = self.run_check(description, "word " * 13)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Title: 13/12 OVER", result.stdout)
        self.assertRegex(result.stdout, r"Scenario 1: \d+/45 OVER")
        self.assertNotIn("/250 OVER", result.stdout)

    def test_rejects_overlong_total_when_each_scenario_fits(self):
        first, rest = self.description.split("**Scenario 1:", 1)
        scenario, evidence = rest.split("## Evidence and references", 1)
        description = first + "".join(
            f"**Scenario {number}:{scenario}" for number in range(1, 10)
        ) + "## Evidence and references" + evidence
        result = self.run_check(description)
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"Description: \d+/250 OVER")
        self.assertNotIn("/45 OVER", result.stdout)

    def test_rejects_description_without_required_heading(self):
        result = self.run_check(self.description.replace("## Evidence and references", ""))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Use the four template headings in order", result.stderr)
