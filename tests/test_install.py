import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
if not POWERSHELL and os.name == "nt":
    candidate = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    if candidate.is_file():
        POWERSHELL = str(candidate)
INSTALLERS = (["powershell"] if POWERSHELL else []) + (
    ["bash"] if os.name != "nt" and shutil.which("bash") else []
)
SKILLS = sorted(path for path in (ROOT / "skills").iterdir() if (path / "SKILL.md").is_file())


@unittest.skipUnless(INSTALLERS, "needs PowerShell or POSIX bash")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # Resolve so symlinked temp roots (macOS /var -> /private/var) compare equal.
        self.root = Path(temporary.name).resolve()

    def directories(self, installer):
        root = self.root / installer
        return root / "claude skills", root / "copilot skills"

    def run_installer(self, installer, client=None):
        claude, copilot = self.directories(installer)
        env = {**os.environ, "CLAUDE_SKILLS_DIR": str(claude), "COPILOT_SKILLS_DIR": str(copilot)}
        if installer == "powershell":
            command = [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                       "-File", str(ROOT / "install.ps1")]
            if client is not None:
                command += ["-Client", client]
        else:
            command = ["bash", str(ROOT / "install.sh")]
            if client is not None:
                command += ["--client", client]
        return subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)

    def assert_installed(self, target):
        self.assertEqual(sorted(path.name for path in target.iterdir()),
                         [path.name for path in SKILLS])
        for source in SKILLS:
            self.assertEqual((target / source.name).resolve(), source.resolve())

    def test_default_preserves_claude_only_installation(self):
        for installer in INSTALLERS:
            with self.subTest(installer=installer):
                result = self.run_installer(installer)
                self.assertEqual(result.returncode, 0, result.stderr)
                claude, copilot = self.directories(installer)
                self.assert_installed(claude)
                self.assertFalse(copilot.exists())

    def test_copilot_installation_does_not_change_claude(self):
        for installer in INSTALLERS:
            with self.subTest(installer=installer):
                result = self.run_installer(installer, "copilot")
                self.assertEqual(result.returncode, 0, result.stderr)
                claude, copilot = self.directories(installer)
                self.assert_installed(copilot)
                self.assertFalse(claude.exists())

    def test_both_clients_share_sources_and_reruns_are_idempotent(self):
        for installer in INSTALLERS:
            with self.subTest(installer=installer):
                first = self.run_installer(installer, "both")
                self.assertEqual(first.returncode, 0, first.stderr)
                second = self.run_installer(installer, "both")
                self.assertEqual(second.returncode, 0, second.stderr)
                for target in self.directories(installer):
                    self.assert_installed(target)
                self.assertEqual(second.stdout.count("already linked"), 2 * len(SKILLS))

    def test_artifact_template_is_available_through_both_client_installations(self):
        skill = "research-and-produce-artifact"
        template = ROOT / "skills" / skill / "assets" / "explainer.html"
        self.assertTrue(template.is_file(), "The artifact skill must bundle its HTML template")
        for installer in INSTALLERS:
            with self.subTest(installer=installer):
                result = self.run_installer(installer, "both")
                self.assertEqual(result.returncode, 0, result.stderr)
                for target in self.directories(installer):
                    installed = target / skill / "assets" / "explainer.html"
                    self.assertEqual(installed.resolve(), template.resolve())
                    self.assertEqual(installed.read_bytes(), template.read_bytes())

    def test_existing_skill_directory_is_preserved(self):
        for installer in INSTALLERS:
            with self.subTest(installer=installer):
                claude, copilot = self.directories(installer)
                existing = copilot / SKILLS[0].name
                existing.mkdir(parents=True)
                marker = existing / "SKILL.md"
                marker.write_text("locally maintained\n")
                result = self.run_installer(installer, "copilot")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(marker.read_text(), "locally maintained\n")
                self.assertEqual(existing.resolve(), existing)
                self.assertFalse(claude.exists())
                for source in SKILLS[1:]:
                    self.assertEqual((copilot / source.name).resolve(), source.resolve())

    def test_link_to_another_skill_is_preserved(self):
        for installer in INSTALLERS:
            with self.subTest(installer=installer):
                _, copilot = self.directories(installer)
                copilot.mkdir(parents=True)
                elsewhere = self.root / (installer + "-elsewhere")
                elsewhere.mkdir()
                existing = copilot / SKILLS[0].name
                if os.name == "nt":
                    script = f"New-Item -ItemType Junction -Path '{existing}' -Target '{elsewhere}'"
                    subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
                                   check=True, capture_output=True, text=True)
                else:
                    existing.symlink_to(elsewhere, target_is_directory=True)
                result = self.run_installer(installer, "copilot")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(existing.resolve(), elsewhere.resolve())
                self.assertIn("skip", result.stdout + result.stderr)

    def test_invalid_client_creates_no_installation(self):
        for installer in INSTALLERS:
            with self.subTest(installer=installer):
                result = self.run_installer(installer, "unknown")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(path.exists() for path in self.directories(installer)))
