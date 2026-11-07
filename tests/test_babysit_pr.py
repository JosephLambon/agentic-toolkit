"""Tests for skills/babysit-pr/scripts/babysit.py.

Uses a fake `gh` on PATH that answers from fixture JSON, and real git repos in a temp
folder, so no network or GitHub account is needed.
"""
import importlib.util
import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/babysit-pr/scripts/babysit.py"
_spec = importlib.util.spec_from_file_location("babysit", SCRIPT)
babysit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(babysit)

FAKE_GH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    with open(os.environ["FAKE_GH_LOG"], "a") as log:
        log.write(json.dumps(args) + "\\n")
    fixtures = json.load(open(os.environ["FAKE_GH_FIXTURES"]))
    if args[:2] == ["pr", "view"]:
        print(json.dumps(fixtures["pr"]))
    elif args[:2] == ["pr", "checks"]:
        print(json.dumps(fixtures["checks"]))
    elif args[:2] == ["api", "user"]:
        print(fixtures["user"])
    elif args[0] == "api" and args[1].startswith("repos/"):
        print(fixtures.get("protected", "false"))
    elif args[:2] == ["api", "graphql"]:
        query = args[3]
        for key in ("addPullRequestReviewThreadReply", "addComment", "resolveReviewThread",
                    "minimizeComment", "nodes(ids", "node(id", "reviewThreads", "pullRequest"):
            if key in query:
                value = fixtures[key]
                if isinstance(value, dict) and "__raw" in value:
                    print(json.dumps(value["__raw"]))
                    sys.exit(value["__exit"])
                print(json.dumps({"data": value}))
                break
    else:
        sys.exit("fake gh: unexpected " + " ".join(args))
""")

PR_URL = "https://github.com/acme/widget/pull/7"
BOT = {"__typename": "Bot", "login": "copilot-pull-request-reviewer"}
USER = {"__typename": "User", "login": "someone"}


def thread(tid, author, resolved=False, opener=None):
    return {"id": tid, "isResolved": resolved, "isOutdated": False, "path": "a.py", "line": 3,
            "opener": {"nodes": [{"author": opener or author}]},
            "latest": {"nodes": [{"id": tid + "-c", "url": "u", "body": "fix this", "author": author}]}}


def comment(cid, author, updated="1", minimized=False, body="please fix", editor=None):
    return {"id": cid, "url": "https://x/" + cid, "body": body, "updatedAt": updated,
            "isMinimized": minimized, "author": author, "editor": editor}


def list_fixture(comment_updated="1"):
    return {"repository": {"pullRequest": {
        "state": "OPEN", "headRefOid": "abcdef123456",
        "reviewThreads": {"pageInfo": {"hasPreviousPage": False}, "nodes": [
            thread("PRRT_new", BOT), thread("PRRT_done", BOT, resolved=True),
            thread("PRRT_ours", USER), thread("PRRT_person", BOT, opener=USER)]},
        "comments": {"pageInfo": {"hasPreviousPage": False}, "nodes": [
            comment("IC_bot", BOT, comment_updated), comment("IC_hidden", BOT, minimized=True),
            comment("IC_person", USER), comment("IC_edited", BOT, editor=USER)]},
        "reviews": {"pageInfo": {"hasPreviousPage": True}, "nodes": [
            comment("PRR_empty", BOT, body=" "), comment("PRR_bot", BOT, body="<!-- x -->Overview")]},
        "commits": {"nodes": [{"commit": {"statusCheckRollup": {"contexts": {"nodes": [
            {"__typename": "CheckRun", "name": "ci", "conclusion": "FAILURE"},
            {"__typename": "StatusContext", "context": "lint", "state": "SUCCESS"}]}}}}]}}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text(FAKE_GH)
        (bin_dir / "gh").chmod(0o755)
        self.log = self.tmp / "gh.log"
        self.fixtures = self.tmp / "fixtures.json"
        self.env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                    "FAKE_GH_LOG": str(self.log), "FAKE_GH_FIXTURES": str(self.fixtures),
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        self.saved_env = dict(os.environ)
        os.environ.update(self.env)
        self.saved = (babysit.STATE_ROOT, babysit.CHECKS_APPEAR, babysit.POLL)
        babysit.STATE_ROOT, babysit.CHECKS_APPEAR, babysit.POLL = self.tmp / "state", 0, 0
        self.set_fixtures()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved_env)
        babysit.STATE_ROOT, babysit.CHECKS_APPEAR, babysit.POLL = self.saved
        subprocess.run(["rm", "-rf", str(self.tmp)])

    def set_fixtures(self, **overrides):
        data = {"reviewThreads": list_fixture(),
                "pullRequest": {"repository": {"pullRequest": {"id": "PR_1"}}},
                "node(id": {"node": {"url": "https://x/IC_bot"}},
                "addPullRequestReviewThreadReply": {"addPullRequestReviewThreadReply": {"comment": {"url": "r1"}}},
                "addComment": {"addComment": {"commentEdge": {"node": {"url": "r2"}}}},
                "resolveReviewThread": {"resolveReviewThread": {"thread": {"isResolved": True}}},
                "minimizeComment": {"minimizeComment": {"minimizedComment": {"isMinimized": True}}}, "user": "me",
                "checks": [{"name": "ci", "bucket": "fail"}, {"name": "lint", "bucket": "pass"}],
                "pr": {"state": "OPEN", "headRefOid": "", "headRefName": "feature", "isCrossRepository": False,
                       "maintainerCanModify": False, "headRepository": {"name": "widget"},
                       "headRepositoryOwner": {"login": "acme"}}}
        data.update(overrides)
        self.fixtures.write_text(json.dumps(data))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []


class FeedbackTests(Base):
    def test_list_keeps_only_new_bot_feedback(self):
        out = babysit.list_items(babysit.PR(PR_URL))
        self.assertEqual([i["id"] for i in out["items"]], ["PRRT_new", "IC_bot", "PRR_bot"])
        self.assertEqual(out["failing_checks"], ["ci"])
        self.assertEqual(out["items"][2]["excerpt"], "Overview")
        self.assertEqual(out["warnings"], ["Only the newest 100 reviews were checked."])
        self.assertFalse(out["busy"])

    def test_list_reports_busy_while_a_fixer_holds_the_lock(self):
        pr = babysit.PR(PR_URL)
        babysit.list_items(pr)
        pr.lock.write_text("x")
        self.assertTrue(babysit.list_items(pr)["busy"])
        babysit.done(pr)
        self.assertFalse(babysit.list_items(pr)["busy"])

    def test_show_flags_bots_and_skips_deleted_items(self):
        bot = {"__typename": "IssueComment", "id": "IC_bot", "url": "u", "body": "b<!-- s -->",
               "author": BOT, "editor": None}
        edited = dict(bot, id="IC_edited", editor=USER)
        self.set_fixtures(**{"nodes(ids": {"__exit": 1, "__raw": {
            "data": {"nodes": [bot, None, edited]},
            "errors": [{"type": "NOT_FOUND", "message": "Could not resolve"}]}}})
        out = babysit.show(babysit.PR(PR_URL), ["IC_bot", "IC_gone", "IC_edited"])
        self.assertEqual([(i["id"], i["bot"], i["body"]) for i in out["items"]],
                         [("IC_bot", True, "b"), ("IC_edited", False, "b")])
        self.assertEqual(out["deleted"], ["IC_gone"])

    def test_reply_to_a_deleted_comment_fails(self):
        self.set_fixtures(**{"node(id": {"__exit": 1, "__raw": {
            "data": {"node": None}, "errors": [{"type": "NOT_FOUND", "message": "Could not resolve"}]}}})
        with self.assertRaises(babysit.Fail):
            babysit.reply(babysit.PR(PR_URL), "IC_gone", "Fixed.")

    def test_seen_hides_items_until_a_bot_edits_them(self):
        pr = babysit.PR(PR_URL)
        babysit.list_items(pr)
        out = babysit.mark_seen(pr, ["PRRT_new", "IC_bot", "PRRT_other"])
        self.assertEqual(out["not_in_last_list"], ["PRRT_other"])
        self.assertEqual([i["id"] for i in babysit.list_items(pr)["items"]], ["PRR_bot"])
        self.set_fixtures(reviewThreads=list_fixture(comment_updated="2"))
        self.assertIn("IC_bot", [i["id"] for i in babysit.list_items(pr)["items"]])

    def test_reply_refuses_mentions_outside_code(self):
        with self.assertRaises(babysit.Fail) as err:
            babysit.reply(babysit.PR(PR_URL), "PRRT_new", "Thanks @coderabbitai")
        self.assertEqual(err.exception.code, 2)
        self.assertEqual(self.calls(), [])
        babysit.reply(babysit.PR(PR_URL), "PRRT_new", "Used `@property`; mail a@b.com.")

    def test_reply_threads_in_place_and_links_comments(self):
        pr = babysit.PR(PR_URL)
        babysit.reply(pr, "PRRT_new", "Fixed in abc123.")
        babysit.reply(pr, "IC_bot", "All fixed.")
        bodies = [a for call in self.calls() for a in call if a.startswith("body=")]
        self.assertEqual(bodies, ["body=**babysit-pr:** Fixed in abc123.",
                                  "body=Re: https://x/IC_bot\n\n**babysit-pr:** All fixed."])

    def test_checks_waits_for_the_pushed_head_and_slow_checks(self):
        pr = babysit.PR(PR_URL)
        pr.save({"pushed": "abc1234def"})
        self.set_fixtures(pr={"headRefOid": "abc1234def"}, checks=[{"name": "fast", "bucket": "pass"}])
        clock = [0]

        def sleep(_):
            clock[0] += 60
            self.set_fixtures(pr={"headRefOid": "abc1234def"},
                              checks=[{"name": "fast", "bucket": "pass"}, {"name": "slow", "bucket": "fail"}])
        babysit.CHECKS_APPEAR = 120
        with mock.patch.object(babysit.time, "time", lambda: clock[0]), \
                mock.patch.object(babysit.time, "sleep", sleep):
            out = babysit.checks(pr)
        self.assertEqual(out, {"head": "abc1234", "failed": ["slow"], "pending": [], "passed": 1})
        babysit.CHECKS_APPEAR = 0
        self.set_fixtures(pr={"headRefOid": "fff0000"})
        self.assertEqual(babysit.checks(pr)["checks"], "PR head moved past your push")

    def test_resolve_and_hide_check_the_kind(self):
        pr = babysit.PR(PR_URL)
        for func, item in ((babysit.resolve, "IC_bot"), (babysit.hide, "PRRT_new"),
                           (babysit.hide, "PRRC_x")):
            with self.assertRaises(babysit.Fail):
                func(pr, item)
        babysit.resolve(pr, "PRRT_new")
        babysit.hide(pr, "PRR_bot")


class GitTests(Base):
    def git(self, *args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                              text=True).stdout.strip()

    def setUp(self):
        super().setUp()
        bare = self.tmp / "acme" / "widget.git"
        self.git("init", "--quiet", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        self.clone = self.tmp / "clone"
        self.git("clone", "--quiet", str(bare), str(self.clone), cwd=self.tmp)
        (self.clone / "a.txt").write_text("one\n")
        self.git("add", ".", cwd=self.clone)
        self.git("commit", "--quiet", "-m", "one", cwd=self.clone)
        self.git("push", "--quiet", "origin", "HEAD:refs/heads/feature", cwd=self.clone)
        self.cwd = os.getcwd()
        os.chdir(self.clone)

    def tearDown(self):
        os.chdir(self.cwd)
        super().tearDown()

    def commit_in(self, folder, name):
        (folder / name).write_text(name)
        self.git("add", ".", cwd=folder)
        self.git("commit", "--quiet", "-m", name, cwd=folder)

    def test_start_push_sync_stop(self):
        pr = babysit.PR(PR_URL)
        out = babysit.start(pr, str(self.tmp / "wt"))
        self.assertEqual(out["push"], {"remote": "origin", "branch": "feature"})
        wt = Path(out["worktree"])
        self.commit_in(wt, "fix1")
        babysit.push(pr)
        self.assertEqual(self.git("ls-remote", "origin", "feature", cwd=self.clone).split()[0],
                         self.git("rev-parse", "HEAD", cwd=wt))

        self.git("fetch", "--quiet", "origin", "feature", cwd=self.clone)
        self.git("checkout", "--quiet", "-B", "feature", "FETCH_HEAD", cwd=self.clone)
        self.commit_in(self.clone, "theirs")
        self.git("push", "--quiet", "origin", "feature", cwd=self.clone)
        self.commit_in(wt, "fix2")
        with self.assertRaises(babysit.Fail) as err:
            babysit.push(pr)
        self.assertEqual(err.exception.code, 3)
        self.assertIn("Rebased 1", babysit.sync(pr)["warnings"][0])
        babysit.push(pr)
        self.assertTrue((wt / "theirs").exists())

        (wt / "untracked").write_text("x")
        self.assertEqual(babysit.sync(pr)["warnings"], [])
        (wt / "a.txt").write_text("changed")
        with self.assertRaises(babysit.Fail):
            babysit.sync(pr)
        with self.assertRaises(babysit.Fail):
            babysit.stop(pr)
        babysit.done(pr)
        with self.assertRaises(babysit.Fail):
            babysit.stop(pr)
        babysit.stop(pr, force=True)
        self.assertFalse(wt.exists())
        self.assertTrue(pr.state_file.exists())
        self.assertEqual(babysit.start(pr, str(wt))["worktree"], str(wt))

    def test_sync_does_not_restore_a_pushed_commit_the_owner_dropped(self):
        pr = babysit.PR(PR_URL)
        wt = Path(babysit.start(pr, str(self.tmp / "wt"))["worktree"])
        before = self.git("rev-parse", "HEAD", cwd=wt)
        self.commit_in(wt, "fix")
        babysit.push(pr)
        self.git("push", "--quiet", "--force", "origin", f"{before}:refs/heads/feature", cwd=self.clone)
        self.assertEqual(babysit.sync(pr)["warnings"], [])
        self.assertFalse((wt / "fix").exists())

    def test_push_refused_by_the_server_is_not_head_moved(self):
        pr = babysit.PR(PR_URL)
        wt = Path(babysit.start(pr, str(self.tmp / "wt"))["worktree"])
        hook = self.tmp / "acme" / "widget.git" / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        self.commit_in(wt, "fix")
        with self.assertRaises(babysit.Fail) as err:
            babysit.push(pr)
        self.assertEqual(err.exception.code, 1)
        self.assertIn("Push failed", str(err.exception))

    def test_failed_push_blocks_until_the_head_changes(self):
        pr = babysit.PR(PR_URL)
        wt = Path(babysit.start(pr, str(self.tmp / "wt"))["worktree"])
        hook = self.tmp / "acme" / "widget.git" / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        self.commit_in(wt, "fix")
        with self.assertRaises(babysit.Fail):
            babysit.push(pr)
        synced = pr.load()["synced"]
        listing = list_fixture()
        listing["repository"]["pullRequest"]["headRefOid"] = synced
        self.set_fixtures(reviewThreads=listing)
        self.assertIn("Push failed", babysit.list_items(pr)["blocked"])
        self.set_fixtures()
        self.assertNotIn("blocked", babysit.list_items(pr))

        babysit.done(pr)
        with self.assertRaises(babysit.Fail) as err:
            babysit.stop(pr)
        self.assertIn("never pushed", str(err.exception))
        babysit.stop(pr, force=True)
        self.assertFalse(wt.exists())

    def test_sync_recreates_a_vanished_worktree_and_push_refuses_a_merged_pr(self):
        pr = babysit.PR(PR_URL)
        wt = Path(babysit.start(pr, str(self.tmp / "wt"))["worktree"])
        subprocess.run(["rm", "-rf", str(wt)])
        babysit.sync(pr)
        self.assertTrue((wt / "a.txt").exists())
        self.commit_in(wt, "fix")
        self.set_fixtures(pr={"state": "MERGED"})
        with self.assertRaises(babysit.Fail) as err:
            babysit.push(pr)
        self.assertEqual(err.exception.code, 2)

    def test_protected_head_branch_means_patches(self):
        self.set_fixtures(protected="true")
        out = babysit.start(babysit.PR(PR_URL), str(self.tmp / "wt"))
        self.assertIsNone(out["push"])
        self.assertIn("protected", out["warnings"][0])

    def test_start_refuses_closed_pr_and_fork_without_edits_cant_push(self):
        self.set_fixtures(pr={"state": "MERGED"})
        with self.assertRaises(babysit.Fail):
            babysit.start(babysit.PR(PR_URL))
        self.set_fixtures(pr={"state": "OPEN", "headRefName": "feature", "isCrossRepository": True,
                              "maintainerCanModify": False, "headRepository": {"name": "widget"},
                              "headRepositoryOwner": {"login": "stranger"}})
        self.git("push", "--quiet", "origin", "HEAD:refs/pull/7/head", cwd=self.clone)
        out = babysit.start(babysit.PR(PR_URL))
        self.assertIsNone(out["push"])
        self.assertEqual(len(out["warnings"]), 2)
        with self.assertRaises(babysit.Fail) as err:
            babysit.push(babysit.PR(PR_URL))
        self.assertEqual(err.exception.code, 2)
        self.assertIn("format-patch -o", str(err.exception))

    def test_own_fork_pushes_to_the_fork_without_warnings(self):
        fork_url = "https://github.com/me/widget.git"
        self.git("config", f"url.{self.tmp / 'acme' / 'widget.git'}.insteadOf", fork_url, cwd=self.clone)
        self.set_fixtures(pr={"state": "OPEN", "headRefName": "feature", "isCrossRepository": True,
                              "maintainerCanModify": False, "headRepository": {"name": "widget"},
                              "headRepositoryOwner": {"login": "me"}})
        out = babysit.start(babysit.PR(PR_URL), str(self.tmp / "wt"))
        self.assertEqual((out["push"], out["warnings"]), ({"url": fork_url, "branch": "feature"}, []))


if __name__ == "__main__":
    unittest.main()
