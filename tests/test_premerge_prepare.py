"""Tests for skills/premerge-swarm-review/scripts/prepare.py.

Uses real git repos in a temp folder and a fake `gh` on PATH that prints
fixture JSON, so no network or GitHub account is needed.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/premerge-swarm-review/scripts/prepare.py"
_spec = importlib.util.spec_from_file_location("prepare", SCRIPT)
prepare_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prepare_mod)

FAKE_GH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import os, sys
    args = sys.argv[1:]
    with open(os.environ["FAKE_GH_LOG"], "a") as log:
        log.write(" ".join(args) + "\\n")
    if args[:2] == ["pr", "view"]:
        print(open(os.environ["FAKE_PR_JSON"]).read())
    elif args[:2] == ["repo", "view"]:
        print('{"visibility": "PUBLIC"}')
    else:
        sys.exit("fake gh: unexpected " + " ".join(args))
""")

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True,
                          capture_output=True, text=True).stdout.strip()


class PrepareTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

        # Upstream bare repo at .../acme/widgets.git with main and refs/pull/7/head.
        self.upstream = self.root / "acme" / "widgets.git"
        self.upstream.parent.mkdir()
        git("init", "--quiet", "--bare", "-b", "main", str(self.upstream), cwd=self.root)
        self.seed = self.root / "seed"
        git("init", "--quiet", "-b", "main", str(self.seed), cwd=self.root)
        (self.seed / "app.txt").write_text("v1\n")
        git("add", ".", cwd=self.seed)
        git("commit", "--quiet", "-m", "base", cwd=self.seed)
        self.base_sha = git("rev-parse", "HEAD", cwd=self.seed)
        git("checkout", "--quiet", "-b", "feature", cwd=self.seed)
        (self.seed / "app.txt").write_text("v2\n")
        git("commit", "--quiet", "-am", "change", cwd=self.seed)
        self.head_sha = git("rev-parse", "HEAD", cwd=self.seed)
        git("push", "--quiet", str(self.upstream), "main", "feature:refs/pull/7/head",
            cwd=self.seed)

        self.clone = self.root / "clone"
        git("clone", "--quiet", str(self.upstream), str(self.clone), cwd=self.root)

        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text(FAKE_GH)
        (bin_dir / "gh").chmod(0o755)
        self.pr_json = self.root / "pr.json"
        self.gh_log = self.root / "gh.log"
        self.env = {**GIT_ENV, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                    "FAKE_PR_JSON": str(self.pr_json), "FAKE_GH_LOG": str(self.gh_log)}
        self.out = self.root / "out"

    def write_pr(self, **overrides):
        pr = {"number": 7, "url": "https://github.com/acme/widgets/pull/7", "title": "Change",
              "author": {"login": "dev"}, "state": "OPEN", "isDraft": False,
              "headRefName": "feature", "headRefOid": self.head_sha, "baseRefName": "main",
              "mergeable": "MERGEABLE", "maintainerCanModify": False,
              "isCrossRepository": False, "headRepository": {"name": "widgets"},
              "headRepositoryOwner": {"login": "acme"}}
        pr.update(overrides)
        self.pr_json.write_text(json.dumps(pr))

    def run_script(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.clone,
                              env=self.env, capture_output=True, text=True)

    def prepare(self, *args, **overrides):
        self.write_pr(**overrides)
        result = self.run_script(*(args or ("7",)), "--out", str(self.out))
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_makes_worktrees_at_head_and_merge_base(self):
        data = self.prepare()
        self.assertEqual((data["repo"], data["head"], data["mergeBase"]),
                         ("acme/widgets", self.head_sha, self.base_sha))
        self.assertEqual(data["visibility"], "PUBLIC")
        self.assertEqual(data["warnings"], [])
        self.assertEqual(data["push"], {"remote": "origin", "branch": "feature"})
        for role in ("feature", "bugs", "performance", "security"):
            tree = data["worktrees"][role]
            self.assertEqual(git("rev-parse", "HEAD", cwd=tree), self.head_sha)
            self.assertEqual((Path(tree) / "app.txt").read_text(), "v2\n")
        self.assertEqual(git("rev-parse", "HEAD", cwd=data["worktrees"]["base"]), self.base_sha)
        self.assertTrue(Path(data["reports"]).is_dir())

    def test_behind_base_warns_and_baseline_stays_at_merge_base(self):
        git("checkout", "--quiet", "main", cwd=self.seed)
        (self.seed / "other.txt").write_text("x\n")
        git("add", ".", cwd=self.seed)
        git("commit", "--quiet", "-m", "newer base", cwd=self.seed)
        git("push", "--quiet", str(self.upstream), "main", cwd=self.seed)
        data = self.prepare()
        self.assertEqual(len(data["warnings"]), 1)
        self.assertIn("behind main by 1 commits", data["warnings"][0])
        self.assertNotEqual(data["baseTip"], data["mergeBase"])
        self.assertEqual(git("rev-parse", "HEAD", cwd=data["worktrees"]["base"]), self.base_sha)

    def test_warns_on_fork_draft_conflicts_and_unknown(self):
        data = self.prepare(isCrossRepository=True, isDraft=True, mergeable="CONFLICTING")
        self.assertEqual(len(data["warnings"]), 3)
        self.assertIn("fork PR by dev", data["warnings"][0])
        self.assertIsNone(data["push"])
        self.assertIn("conflicts", data["warnings"][2])
        self.out = self.root / "out2"
        data = self.prepare(mergeable="UNKNOWN")
        self.assertIn("mergeability", data["warnings"][0])

    def test_fork_push_target_needs_maintainer_edits(self):
        data = self.prepare(isCrossRepository=True, maintainerCanModify=True,
                            headRepositoryOwner={"login": "dev"})
        self.assertEqual(data["push"], {"url": "https://github.com/dev/widgets.git",
                                        "branch": "feature"})

    def test_refuses_when_head_moved(self):
        self.write_pr(headRefOid="0" * 40)
        result = self.run_script("7", "--out", str(self.out))
        self.assertEqual(result.returncode, 1)
        self.assertIn("pushed to during setup", result.stderr)
        self.assertFalse(self.out.exists())

    def test_refuses_closed_pr(self):
        self.write_pr(state="MERGED")
        result = self.run_script("7", "--out", str(self.out))
        self.assertEqual(result.returncode, 3)
        self.assertIn("MERGED", result.stderr)

    def test_needs_a_clone_of_the_pr_repo(self):
        self.write_pr(url="https://github.com/other/thing/pull/7")
        result = self.run_script("7", "--out", str(self.out))
        self.assertEqual(result.returncode, 2)
        self.assertIn("gh repo clone other/thing", result.stderr)

    def test_never_overwrites_existing_worktree_paths(self):
        self.write_pr()
        (self.out / "wt-bugs").mkdir(parents=True)
        result = self.run_script("7", "--out", str(self.out))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Choose a new --out", result.stderr)

    def test_passes_repo_through_and_finds_a_non_origin_remote(self):
        git("remote", "rename", "origin", "upstream", cwd=self.clone)
        git("remote", "add", "origin", str(self.root / "dev" / "widgets.git"), cwd=self.clone)
        data = self.prepare("7", "--repo", "acme/widgets")
        self.assertEqual(data["push"]["remote"], "upstream")
        calls = self.gh_log.read_text().splitlines()
        self.assertTrue(calls[0].startswith("pr view 7 --json") and calls[0].endswith("--repo acme/widgets"))
        self.assertEqual(calls[1], "repo view github.com/acme/widgets --json visibility")

    def test_failed_setup_can_still_be_cleaned_up(self):
        self.write_pr()
        real_run = prepare_mod.run

        def failing_run(cmd):
            if "worktree" in cmd and "add" in cmd and any("wt-performance" in c for c in cmd):
                raise prepare_mod.Fail("simulated failure")
            return real_run(cmd)

        os.environ["PATH"], old_path = self.env["PATH"], os.environ["PATH"]
        os.environ.update(FAKE_PR_JSON=str(self.pr_json), FAKE_GH_LOG=str(self.gh_log))
        cwd = os.getcwd()
        try:
            os.chdir(self.clone)
            prepare_mod.run = failing_run
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(prepare_mod.main(["7", "--out", str(self.out)]), 1)
        finally:
            prepare_mod.run = real_run
            os.chdir(cwd)
            os.environ["PATH"] = old_path
        result = self.run_script("--cleanup", "--out", str(self.out), cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["removed"]), 2)

    @unittest.skipUnless(shutil.which("lsof"), "needs lsof")
    def test_cleanup_stops_processes_running_in_worktrees(self):
        data = self.prepare()
        server = subprocess.Popen(["sleep", "60"], cwd=data["worktrees"]["bugs"])
        self.addCleanup(server.kill)
        result = self.run_script("--cleanup", "--out", str(self.out), cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(server.pid, json.loads(result.stdout)["stopped"])
        self.assertEqual(server.wait(timeout=10), -15)

    def test_cleanup_from_another_folder_removes_only_its_worktrees(self):
        self.prepare()
        other = self.root / "keep"
        git("worktree", "add", "--quiet", "--detach", str(other), "HEAD", cwd=self.clone)
        result = self.run_script("--cleanup", "--out", str(self.out), cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["removed"]), 5)
        listed = git("worktree", "list", cwd=self.clone)
        self.assertNotIn("wt-", listed)
        self.assertIn(str(other), listed)

    def test_cleanup_without_state_fails(self):
        result = self.run_script("--cleanup", "--out", str(self.out))
        self.assertEqual(result.returncode, 1)
        self.assertIn("nothing prepared", result.stderr)


if __name__ == "__main__":
    unittest.main()
