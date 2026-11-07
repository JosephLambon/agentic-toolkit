#!/usr/bin/env python3
"""Pin a GitHub PR's head commit and make one worktree per reviewer.

Usage:
  python3 prepare.py PR --out DIR [--repo OWNER/REPO]
  python3 prepare.py --scan --out DIR
  python3 prepare.py --cleanup --out DIR

PR is a number, URL or branch; prefer the URL (or pass --repo), because in a
fork's clone a bare number can resolve to the fork's own PR. Run it from a
clone of the PR's base repo. Creates detached worktrees DIR/wt-feature,
wt-bugs, wt-performance and wt-security at the PR head, DIR/wt-base at the
merge base (so the performance baseline excludes the base branch's newer
commits), DIR/reports/<role>/ for each reviewer's proof files, and
DIR/state.json. Prints one JSON object; act on its "warnings". "evidence" is
the evidenced-pull-request skill folder, whose scripts reviewers use for
screenshots and the orchestrator uses to post, or null when that skill or
Node is missing. Each DIR is single-use: a re-run needs a new one.

--scan lists lines in DIR/reports/*.md and DIR/reports/*/*.log that hold
your home folder, username, DIR's path or token-like strings, and exits 1 if
there are any. It can't see inside images.

--cleanup can run from anywhere (it reads DIR/state.json). It stops every
process whose working folder is inside DIR, then removes DIR's worktrees.
It keeps DIR/reports/ and any DIR/fix.patch.

Gotchas:
- It fetches refs/pull/N/head, not the branch name, because a fork PR's
  branch doesn't exist on the base repo.
- If the PR is pushed to between `gh pr view` and the fetch, the fetched
  commit won't match headRefOid. It stops rather than review the wrong code.
- GitHub reports mergeStateStatus BEHIND only when branch protection needs
  up-to-date branches, so "behind" is worked out from the commits instead.
- state.json is written before any worktree, so a failed setup can still be
  cleaned up.
"""
import argparse
import getpass
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROLES = ("feature", "bugs", "performance", "security")
PR_FIELDS = ("number,url,title,author,state,isDraft,headRefName,headRefOid,baseRefName,"
             "mergeable,maintainerCanModify,isCrossRepository,"
             "headRepository,headRepositoryOwner")
MIN_GH = (2, 103, 0)  # first gh whose --attach resolves --body-file paths from the file's folder
TOKENS = {
    "GitHub token": r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,})",
    "API key": r"\bsk-[\w-]{20,}",
    "AWS key": r"\bAKIA[0-9A-Z]{16}\b",
    "Slack token": r"\bxox[abprs]-[\w-]{10,}",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}
URL_RE = re.compile(r"^(https?://([^/]+))/([^/]+)/([^/]+)/pull/\d+")


class Fail(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def run(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise Fail(f"`{cmd[0]}` isn't installed or isn't on PATH.")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise Fail(f"`{' '.join(cmd)}` failed: {detail}")
    return result.stdout.strip()


def not_a_clone(owner, repo):
    return Fail(f"This folder isn't a clone of {owner}/{repo}. Run "
                f"`gh repo clone {owner}/{repo} <dir>`, then re-run from <dir>.", 2)


def find_remote(owner, repo):
    try:
        run(["git", "rev-parse", "--show-toplevel"])
    except Fail:
        raise not_a_clone(owner, repo)
    pattern = re.compile(rf"[:/]{re.escape(owner)}/{re.escape(repo)}(\.git)?/?$", re.I)
    for name in run(["git", "remote"]).split():
        if pattern.search(run(["git", "remote", "get-url", name])):
            return name
    raise not_a_clone(owner, repo)


def fetch(remote, ref):
    run(["git", "fetch", "--quiet", remote, ref])
    return run(["git", "rev-parse", "FETCH_HEAD"])


def evidence_tools():
    if not shutil.which("node"):
        return None
    sibling = Path(__file__).resolve().parents[2] / "evidenced-pull-request"
    for folder in (sibling, Path.home() / ".claude/skills/evidenced-pull-request"):
        if all((folder / "scripts" / f).exists() for f in ("shoot.mjs", "attachments.mjs")):
            return str(folder.resolve())
    return None


def push_target(info, base_url, remote):
    if not info["isCrossRepository"]:
        return {"remote": remote, "branch": info["headRefName"]}
    if not info["maintainerCanModify"]:
        return None
    owner = info["headRepositoryOwner"]["login"]
    return {"url": f"{base_url}/{owner}/{info['headRepository']['name']}.git",
            "branch": info["headRefName"]}


def prepare(pr, out, repo=None):
    view = ["gh", "pr", "view", pr, "--json", PR_FIELDS] + (["--repo", repo] if repo else [])
    info = json.loads(run(view))
    match = URL_RE.match(info["url"])
    if not match:
        raise Fail(f"Can't read the repo from PR URL {info['url']}")
    base_url, host, owner, name = match.groups()
    if info["state"] != "OPEN":
        raise Fail(f"PR {info['url']} is {info['state']}, not open.", 3)

    out = Path(out).resolve()
    trees = {role: out / f"wt-{role}" for role in ROLES + ("base",)}
    used = [str(p) for p in [*trees.values(), out / "state.json", out / "reports"] if p.exists()]
    if used:
        raise Fail(f"Already used, not overwriting: {', '.join(used)}. Choose a new --out "
                   f"(and run --cleanup --out {out} if that run is finished).")
    remote = find_remote(owner, name)
    toplevel = run(["git", "rev-parse", "--show-toplevel"])
    visibility = json.loads(run(["gh", "repo", "view", f"{host}/{owner}/{name}",
                                 "--json", "visibility"]))["visibility"]

    head = fetch(remote, f"pull/{info['number']}/head")
    if head != info["headRefOid"]:
        raise Fail(f"Fetched {head[:7]} but the PR head is {info['headRefOid'][:7]}: "
                   "it was pushed to during setup. Re-run.")
    base_tip = fetch(remote, info["baseRefName"])
    merge_base = run(["git", "merge-base", base_tip, head])

    warnings = []
    gh_version = re.search(r"(\d+)\.(\d+)\.(\d+)", run(["gh", "--version"]))
    if not gh_version or tuple(map(int, gh_version.groups())) < MIN_GH:
        warnings.append("gh is older than 2.103.0, so screenshots can't be attached to the comments: "
                        "ask the user to upgrade it (for example `brew upgrade gh`) before the reviewers start")
    if info["isCrossRepository"]:
        warnings.append(f"fork PR by {info['author']['login']}: reviewers will run its install "
                        "scripts, tests and code on this machine, with your credentials")
    if info["isDraft"]:
        warnings.append("draft: the author may not think it's ready")
    if merge_base != base_tip:
        behind = run(["git", "rev-list", "--count", f"{head}..{base_tip}"])
        warnings.append(f"behind {info['baseRefName']} by {behind} commits: "
                        "the head isn't what would merge")
    if info["mergeable"] == "CONFLICTING":
        warnings.append(f"conflicts with {info['baseRefName']}")
    elif info["mergeable"] == "UNKNOWN":
        warnings.append(f"GitHub hasn't worked out mergeability yet: check with "
                        f"`gh pr view {info['url']} --json mergeable`")

    out.mkdir(parents=True, exist_ok=True)
    (out / "state.json").write_text(json.dumps({"repoPath": toplevel}))
    for role, path in trees.items():
        run(["git", "worktree", "add", "--quiet", "--detach", str(path),
             merge_base if role == "base" else head])
    for role in ROLES:
        (out / "reports" / role).mkdir(parents=True)
    return {
        "repo": f"{owner}/{name}", "number": info["number"], "url": info["url"],
        "title": info["title"], "author": info["author"]["login"], "visibility": visibility,
        "head": head, "base": info["baseRefName"], "baseTip": base_tip, "mergeBase": merge_base,
        "push": push_target(info, base_url, remote), "evidence": evidence_tools(),
        "worktrees": {role: str(path) for role, path in trees.items()},
        "reports": str(out / "reports"), "warnings": warnings,
    }


def scan(out):
    reports = Path(out).resolve() / "reports"
    if not reports.is_dir():
        raise Fail(f"No {reports}: nothing to scan.")
    literals = {"home folder": re.escape(str(Path.home())), "scratch folder": re.escape(str(reports.parent))}
    user = getpass.getuser()
    if len(user) >= 3:
        literals["username"] = rf"\b{re.escape(user)}\b"
    patterns = {**literals, **TOKENS}
    hits = []
    for path in sorted([*reports.glob("*.md"), *reports.glob("*/*.log")]):
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            kinds = [kind for kind, pattern in patterns.items() if re.search(pattern, line)]
            if kinds:
                hits.append({"file": str(path.relative_to(reports)), "line": number, "kinds": kinds})
    return {"hits": hits}


def stop_processes(out):
    """SIGTERM every process whose working folder is inside out. Needs lsof."""
    try:
        listing = subprocess.run(["lsof", "-a", "-d", "cwd", "-Fpn"],
                                 capture_output=True, text=True).stdout
    except FileNotFoundError:
        return None
    stopped, pid = [], None
    for line in listing.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and pid not in (None, os.getpid()):
            path = Path(line[1:])
            if path == out or out in path.parents:
                try:
                    os.kill(pid, signal.SIGTERM)
                    stopped.append(pid)
                except (ProcessLookupError, PermissionError):
                    pass
    return stopped


def cleanup(out):
    out = Path(out).resolve()
    state = out / "state.json"
    if not state.exists():
        raise Fail(f"No {state}: nothing prepared there.")
    repo = json.loads(state.read_text())["repoPath"]
    stopped = stop_processes(out)
    run(["git", "-C", repo, "worktree", "prune"])
    removed, failed = [], []
    for line in run(["git", "-C", repo, "worktree", "list", "--porcelain"]).splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):]).resolve()
            if path.parent == out and path.name.startswith("wt-"):
                try:
                    run(["git", "-C", repo, "worktree", "remove", "--force", str(path)])
                    removed.append(str(path))
                except Fail as err:
                    failed.append(str(err))
    result = {"stopped": stopped if stopped is not None else "lsof missing: stop servers by hand",
              "removed": removed, "failed": failed}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pr", nargs="?", help="PR URL (preferred), number or branch")
    parser.add_argument("--out", required=True, help="new scratch folder outside the repo")
    parser.add_argument("--repo", help="OWNER/REPO, when PR is a number or branch")
    parser.add_argument("--scan", action="store_true",
                        help="list secrets and local paths in the reports before posting")
    parser.add_argument("--cleanup", action="store_true",
                        help="stop processes in and remove the worktrees under --out")
    args = parser.parse_args(argv)
    if not (args.cleanup or args.scan or args.pr):
        parser.error("PR is required unless --scan or --cleanup is given")
    try:
        if args.cleanup:
            result = cleanup(args.out)
        elif args.scan:
            result = scan(args.out)
        else:
            result = prepare(args.pr, args.out, args.repo)
    except Fail as err:
        print(f"prepare.py: {err}", file=sys.stderr)
        return err.code
    print(json.dumps(result, indent=1))
    return 1 if result.get("failed") or result.get("hits") else 0


if __name__ == "__main__":
    sys.exit(main())
