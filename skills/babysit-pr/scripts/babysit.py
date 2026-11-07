#!/usr/bin/env python3
"""GitHub and git plumbing for the babysit-pr skill. Every command takes the PR's URL.

  start   <pr> [--worktree P]  From a clone of the PR's repo: check the PR is open, work out
                               where fixes can be pushed, make (or reuse) a worktree at P.
                               Clears any `blocked` record.
  list    <pr>              New bot feedback, the PR's state, failing checks, `busy` while a
                            fixer holds the lock, `blocked` while the last block still applies.
  claim   <pr>              Take the lock (the tick runs this before spawning a fixer).
  show    <pr> <id>...      Full text of the given items. JSON out.
  seen    <pr> <id>...      Mark items handled, at the version `list` last returned.
  sync    <pr>              Move the worktree to the PR's head, rebasing local commits that
                            were never pushed. Recreates the worktree if it has gone.
  push    <pr>              Push the worktree's HEAD to the PR branch. Never forces.
  checks  <pr>              Wait for CI on the PR head (about 2 to 9 minutes). JSON out.
  reply   <pr> <id> --body-file F   Thread: reply in it. Comment or review: a new PR comment
                            that links it. Prefixes the body with "**babysit-pr:**".
  resolve <pr> <thread id>
  hide    <pr> <id>         Hide a comment or review as Resolved.
  done    <pr>              Release the lock.
  stop    <pr> [--force]    Remove the worktree. Refuses while a fixer is busy or work is
                            unpushed, unless forced. Keeps state, so later runs skip old items.

State lives in ~/.cache/babysit-pr/<host>/<owner>/<repo>/<number>/.

Gotchas:
- Only Bot authors count, and only if no person edited the comment since. Copilot is the Bot
  "copilot-pull-request-reviewer"; GraphQL logins have no "[bot]" suffix.
- A thread counts only if a bot opened it (a bot answering a person's thread doesn't), and
  only while its last comment is a bot's: once we reply, it waits for the bot.
- Comments and reviews can't be resolved, so `seen` (keyed by updatedAt) is their only record,
  and a bot editing its comment makes it new again.
- Ids are GraphQL node ids; the prefix says the kind: PRRT_ thread, IC_ comment, PRR_ review.
- `gh api graphql` exits 1 when any error comes back, even with partial data, so gql() reads
  stdout itself. Only `show` tolerates NOT_FOUND (deleted comments).
- A commit we pushed that the owner later drops (force-push) must not be rebased back on:
  sync skips commits reachable from the last SHA we pushed.
- A failed push or sync records `blocked` against the PR head, so ticks stop spawning fixers
  that would fail the same way. A new head, or `start`, clears it.
- `checks` waits CHECKS_APPEAR seconds even when every registered check has finished, because
  fast checks register before slow workflows do.
- Checks the newest 100 threads, comments and reviews; `warnings` says if there were more.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

URL_RE = re.compile(r"^https?://([^/]+)/([^/]+)/([^/]+)/pull/(\d+)")
MENTION_RE = re.compile(r"(?<![\w`/.-])@[A-Za-z0-9][A-Za-z0-9-]*")
HEAD_MOVED_RE = re.compile(r"\[rejected\].*\((non-fast-forward|fetch first)\)")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
FAILED = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR"}
KINDS = {"PRRT": "thread", "IC": "comment", "PRR": "review"}
EXCERPT = 200
LOCK_STALE = 3600       # seconds since a fixer last touched the lock before it's ignored
CHECKS_APPEAR = 120     # seconds to wait for checks to register on a new head
CHECKS_DEADLINE = 540   # total seconds `checks` waits, under the Bash tool's 600 s cap
POLL = 15
STATE_ROOT = Path.home() / ".cache" / "babysit-pr"

WHO = "author{__typename login} editor{__typename}"
LIST_Q = """query($owner:String!,$name:String!,$n:Int!){repository(owner:$owner,name:$name){
pullRequest(number:$n){state headRefOid
reviewThreads(last:100){pageInfo{hasPreviousPage} nodes{id isResolved isOutdated path line
  opener:comments(first:1){nodes{%(w)s}} latest:comments(last:1){nodes{id url body %(w)s}}}}
comments(last:100){pageInfo{hasPreviousPage} nodes{id url body updatedAt isMinimized %(w)s}}
reviews(last:100){pageInfo{hasPreviousPage} nodes{id url body updatedAt isMinimized %(w)s}}
commits(last:1){nodes{commit{statusCheckRollup{contexts(first:100){nodes{__typename
  ...on CheckRun{name conclusion} ...on StatusContext{context state}}}}}}}}}}""" % {"w": WHO}
SHOW_Q = """query($ids:[ID!]!){nodes(ids:$ids){__typename
...on PullRequestReviewThread{id isResolved isOutdated path line
  comments(first:50){nodes{url body diffHunk %(w)s}}}
...on IssueComment{id url body %(w)s}
...on PullRequestReview{id url body state %(w)s}}}""" % {"w": WHO}
PR_ID_Q = "query($owner:String!,$name:String!,$n:Int!){repository(owner:$owner,name:$name){pullRequest(number:$n){id}}}"
URL_Q = "query($id:ID!){node(id:$id){...on IssueComment{url} ...on PullRequestReview{url}}}"
REPLY_M = "mutation($id:ID!,$body:String!){addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$id,body:$body}){comment{url}}}"
COMMENT_M = "mutation($id:ID!,$body:String!){addComment(input:{subjectId:$id,body:$body}){commentEdge{node{url}}}}"
RESOLVE_M = "mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}"
HIDE_M = "mutation($id:ID!){minimizeComment(input:{subjectId:$id,classifier:RESOLVED}){minimizedComment{isMinimized}}}"


class Fail(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def run(cmd, check=True):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise Fail(f"`{cmd[0]}` isn't installed or isn't on PATH.")
    if check and result.returncode != 0:
        raise Fail(f"`{' '.join(cmd[:3])}` failed: {(result.stderr or result.stdout).strip()}")
    return result


class PR:
    def __init__(self, url):
        m = URL_RE.match(url)
        if not m:
            raise Fail(f"Not a pull request URL: {url}. Get it with `gh pr view <n> --json url`.", 2)
        self.host, self.owner, self.name, n = m.groups()
        self.number = int(n)
        self.url = f"https://{self.host}/{self.owner}/{self.name}/pull/{n}"
        self.dir = STATE_ROOT / self.host / self.owner / self.name / n
        self.state_file = self.dir / "state.json"
        self.lock = self.dir / "lock"

    def gh(self, *args, check=True):
        host = ["--hostname", self.host] if self.host != "github.com" and args[0] == "api" else []
        return run(["gh", *args, *host], check=check)

    def gql(self, query, allow_missing=False, **variables):
        args = ["api", "graphql", "-f", f"query={query}"]
        for key, value in variables.items():
            if isinstance(value, list):
                args += [arg for v in value for arg in ("-f", f"{key}[]={v}")]
            else:
                args += ["-F" if isinstance(value, int) else "-f", f"{key}={value}"]
        result = self.gh(*args, check=False)
        try:
            data = json.loads(result.stdout)
        except ValueError:
            raise Fail(f"`gh api graphql` failed: {(result.stderr or result.stdout).strip()}")
        errors = [e for e in data.get("errors") or []
                  if not (allow_missing and e.get("type") == "NOT_FOUND")]
        if errors or data.get("data") is None:
            raise Fail("GitHub said: " + "; ".join(e.get("message", "?") for e in errors or [{}]))
        return data["data"]

    def repo_vars(self):
        return {"owner": self.owner, "name": self.name, "n": self.number}

    def load(self):
        try:
            return json.loads(self.state_file.read_text())
        except FileNotFoundError:
            return {"seen": {}, "listed": {}}
        except ValueError:
            raise Fail(f"{self.state_file} is corrupt. Delete it (old items will be re-listed).")

    def save(self, state):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1))
        os.replace(tmp, self.state_file)

    def setup(self):
        state = self.load()
        if "worktree" not in state:
            raise Fail(f"No worktree yet. Run `start {self.url}` from a clone of the repo first.", 2)
        return state

    def busy(self):
        return self.lock.exists() and time.time() - self.lock.stat().st_mtime < LOCK_STALE

    def touch(self, create=False):
        if create or self.lock.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            self.lock.write_text(str(time.time()))

    def block(self, state, head, message, code):
        state["blocked"] = {"head": head, "reason": message}
        self.save(state)
        raise Fail(message, code)

    def open_or_fail(self):
        state = json.loads(self.gh("pr", "view", self.url, "--json", "state").stdout)["state"]
        if state != "OPEN":
            raise Fail(f"{self.url} is {state.lower()} now: don't push, reply or resolve.", 2)


def kind(item_id):
    return KINDS.get(item_id.split("_", 1)[0]) or _bad_id(item_id)


def _bad_id(item_id):
    raise Fail(f"Unknown id {item_id}: expected a PRRT_, IC_ or PRR_ id from `list`.", 2)


def from_bot(node):
    """Written by a bot, and not edited since by anyone but a bot."""
    node = node or {}
    editor = node.get("editor")
    return ((node.get("author") or {}).get("__typename") == "Bot"
            and (editor is None or editor.get("__typename") == "Bot"))


def clean(text):
    return COMMENT_RE.sub("", text or "").strip()


def excerpt(text):
    text = " ".join(clean(text).split())
    return text if len(text) <= EXCERPT else text[:EXCERPT - 1] + "…"


def git(*args, wt=None, check=True):
    return run(["git"] + (["-C", str(wt)] if wt else []) + list(args), check=check)


# ---- start / sync / push / checks / stop -------------------------------------------------

def find_remote(owner, name):
    pattern = re.compile(rf"[:/]{re.escape(owner)}/{re.escape(name)}(\.git)?/?$", re.I)
    for remote in git("remote").stdout.split():
        if pattern.search(git("remote", "get-url", remote).stdout.strip()):
            return remote
    return None


def fetch_spec(pr, state):
    return state["fetch"]


def start(pr, worktree=None):
    info = json.loads(pr.gh("pr", "view", pr.url, "--json",
                            "state,headRefName,isCrossRepository,maintainerCanModify,"
                            "headRepository,headRepositoryOwner").stdout)
    if info["state"] != "OPEN":
        raise Fail(f"{pr.url} is {info['state'].lower()}, so there's nothing to babysit.", 2)
    if git("rev-parse", "--show-toplevel", check=False).returncode != 0:
        raise Fail(f"Run this from a clone of {pr.owner}/{pr.name}.", 2)
    branch, warnings = info["headRefName"], []
    upstream = find_remote(pr.owner, pr.name)
    if not info["isCrossRepository"]:
        head_owner, head_name = pr.owner, pr.name
        if not upstream:
            raise Fail(f"No git remote here points at {pr.owner}/{pr.name}. Run this from a clone of it.", 2)
        push = {"remote": upstream, "branch": branch}
    else:
        if not info.get("headRepository"):
            raise Fail("The PR's fork has been deleted, so fixes can't be pushed.", 2)
        head_owner, head_name = info["headRepositoryOwner"]["login"], info["headRepository"]["name"]
        mine = head_owner == pr.gh("api", "user", "--jq", ".login").stdout.strip()
        if not mine:
            warnings.append("This PR is from someone else's fork: running its tests runs its "
                            "author's code here.")
        can_push = mine or info["maintainerCanModify"]
        fork_remote = find_remote(head_owner, head_name)
        push = ({"remote": fork_remote, "branch": branch} if fork_remote else
                {"url": f"https://{pr.host}/{head_owner}/{head_name}.git", "branch": branch})
        if not can_push:
            push = None
            warnings.append("The fork doesn't allow maintainer edits, so fixes can't be pushed. "
                            "They'll be saved as patches and items left open.")
    fetch = ([push.get("remote") or push["url"], branch] if push
             else [upstream, f"pull/{pr.number}/head"])
    if push and pr.gh("api", f"repos/{head_owner}/{head_name}/branches/{branch}", "--jq",
                      ".protected", check=False).stdout.strip() == "true":
        push = None
        warnings.append(f"`{branch}` is a protected branch, so fixes won't be pushed. They'll be "
                        "saved as patches and items left open.")
    if not push and not upstream:
        raise Fail(f"No git remote here points at {pr.owner}/{pr.name}. Run this from a clone of it.", 2)

    wt = Path(worktree).expanduser().resolve() if worktree else (pr.dir / "wt").resolve()
    state = pr.load()
    old = state.get("worktree")
    if old and Path(old) != wt and Path(old).exists():
        warnings.append(f"An older worktree is still at {old}. Check it has nothing unpushed, "
                        f"then `git worktree remove --force {old}`.")
    git_dir = git("rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    state.update(fetch=fetch, git_dir=git_dir, push=push, worktree=str(wt))
    state.pop("blocked", None)
    pr.save(state)
    registered = {Path(line[9:]).resolve() for line in
                  git("worktree", "list", "--porcelain").stdout.splitlines()
                  if line.startswith("worktree ")}
    if wt.exists() and wt not in registered:
        raise Fail(f"{wt} exists but isn't a worktree of this repo. Move it, then re-run.", 2)
    head = sync(pr, lock=False)
    return {"pr": pr.url, "branch": branch, "worktree": str(wt), "push": push,
            "head": head["head"], "warnings": warnings + head["warnings"]}


def ensure_worktree(state, pr):
    wt = state["worktree"]
    if Path(wt).exists():
        if git("rev-parse", "--git-dir", wt=wt, check=False).returncode == 0:
            return wt
        raise Fail(f"{wt} isn't a git worktree any more. Remove it, then re-run `start`.", 2)
    base = ["git", "--git-dir", state["git_dir"]]
    run(base + ["worktree", "prune"])
    run(base + ["fetch", "--quiet", *fetch_spec(pr, state)])
    run(base + ["worktree", "add", "--quiet", "--detach", wt, "FETCH_HEAD"])
    return wt


def sync(pr, lock=True):
    state = pr.setup()
    if lock:
        pr.touch(create=True)
    wt = ensure_worktree(state, pr)
    git("fetch", "--quiet", *fetch_spec(pr, state), wt=wt)
    remote_head = git("rev-parse", "FETCH_HEAD", wt=wt).stdout.strip()
    dirty = git("status", "--porcelain", "--untracked-files=no", wt=wt).stdout.strip()
    if dirty:
        pr.block(state, remote_head, f"The worktree {wt} has uncommitted changes. Commit or "
                 f"discard them, then re-run:\n{dirty}", 3)
    pushed = state.get("pushed")
    if pushed and git("cat-file", "-e", f"{pushed}^{{commit}}", wt=wt, check=False).returncode:
        pushed = None
    exclude = ["--not", pushed] if pushed else []
    local = git("rev-list", "FETCH_HEAD..HEAD", *exclude, wt=wt).stdout.split()
    warnings = []
    if local:
        base = pushed if pushed and not git("merge-base", "--is-ancestor", pushed, "HEAD",
                                            wt=wt, check=False).returncode else "FETCH_HEAD"
        args = ["--onto", "FETCH_HEAD", base] if base != "FETCH_HEAD" else ["FETCH_HEAD"]
        if git("rebase", "--quiet", *args, wt=wt, check=False).returncode != 0:
            conflicts = git("diff", "--name-only", "--diff-filter=U", wt=wt).stdout.split()
            git("rebase", "--abort", wt=wt, check=False)
            pr.block(state, remote_head, f"Rebasing {len(local)} unpushed commit(s) onto the PR "
                     f"head conflicted in: {', '.join(conflicts) or '?'}. Rebase by hand in {wt}.", 3)
        warnings.append(f"Rebased {len(local)} local commit(s) not yet pushed onto the PR head.")
    else:
        git("checkout", "--quiet", "--detach", "FETCH_HEAD", wt=wt)
    state["synced"] = remote_head
    pr.save(state)
    return {"head": git("rev-parse", "--short", "HEAD", wt=wt).stdout.strip(),
            "remote_head": remote_head[:7], "worktree": wt, "warnings": warnings}


def push(pr):
    state = pr.setup()
    pr.touch()
    wt, target = state["worktree"], state["push"]
    if not target:
        raise Fail("Fixes can't be pushed to this PR (see `start`'s warnings). Save them with "
                   f"`git -C {wt} format-patch -o {pr.dir}/patches "
                   f"{state.get('synced', 'FETCH_HEAD')}..HEAD`.", 2)
    pr.open_or_fail()
    dest = target.get("remote") or target["url"]
    result = git("push", "--porcelain", dest, f"HEAD:refs/heads/{target['branch']}", wt=wt,
                 check=False)
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        if HEAD_MOVED_RE.search(detail):
            raise Fail("The PR head moved. Run `sync`, re-run the tests, then push again.", 3)
        pr.block(state, state.get("synced"), "Push failed. If it's a credentials problem, "
                 f"`gh auth setup-git` may fix it:\n{detail}", 1)
    state["pushed"] = git("rev-parse", "HEAD", wt=wt).stdout.strip()
    pr.save(state)
    return {"pushed": state["pushed"][:7], "branch": target["branch"]}


def checks(pr):
    want = pr.load().get("pushed")
    began = time.time()
    while True:
        pr.touch()
        elapsed = time.time() - began
        head = json.loads(pr.gh("pr", "view", pr.url, "--json", "headRefOid").stdout)["headRefOid"]
        result = pr.gh("pr", "checks", pr.url, "--json", "name,bucket", check=False)
        try:
            rows = json.loads(result.stdout or "[]")
        except ValueError:
            rows = []
        registered = bool(rows) and (not want or head == want)
        if not registered and elapsed >= CHECKS_APPEAR:
            moved = want and head != want
            return {"head": head[:7], "checks": "PR head moved past your push" if moved
                    else "none registered"}
        if registered:
            pending = sorted(r["name"] for r in rows if r["bucket"] == "pending")
            if (not pending and elapsed >= CHECKS_APPEAR) or elapsed >= CHECKS_DEADLINE:
                return {"head": head[:7], "failed": sorted(r["name"] for r in rows
                                                           if r["bucket"] in ("fail", "cancel")),
                        "pending": pending,
                        "passed": sum(r["bucket"] == "pass" for r in rows)}
        time.sleep(POLL)


def claim(pr):
    pr.touch(create=True)
    return {"lock": "taken"}


def done(pr):
    pr.lock.unlink(missing_ok=True)
    return {"lock": "released"}


def stop(pr, force=False):
    state = pr.load()
    wt, git_dir = state.get("worktree"), state.get("git_dir")
    if not force:
        if pr.busy():
            raise Fail("A fixer is still working on this PR. Wait for its report, or pass --force.", 2)
        if wt and Path(wt).exists():
            dirty = git("status", "--porcelain", "--untracked-files=no", wt=wt, check=False).stdout.strip()
            known = [s for s in (state.get("synced"), state.get("pushed")) if s]
            unpushed = git("rev-list", "HEAD", "--not", *known, wt=wt, check=False).stdout.split() if known else []
            if dirty or unpushed:
                raise Fail(f"The worktree {wt} has work that was never pushed "
                           f"({len(unpushed)} commit(s){', plus uncommitted changes' if dirty else ''}"
                           f"{': ' + ' '.join(u[:7] for u in unpushed) if unpushed else ''}). "
                           "Save what you need, then pass --force.", 2)
    if git_dir and wt and Path(wt).exists():
        run(["git", "--git-dir", git_dir, "worktree", "remove", "--force", wt])
    if git_dir:
        run(["git", "--git-dir", git_dir, "worktree", "prune"], check=False)
    done(pr)
    return {"stopped": pr.url, "state_kept": str(pr.state_file)}


# ---- feedback ------------------------------------------------------------------------------

def list_items(pr):
    data = pr.gql(LIST_Q, **pr.repo_vars())["repository"]["pullRequest"]
    if not data:
        raise Fail(f"{pr.url} doesn't exist, or this gh account can't see it.", 2)
    state = pr.load()
    seen, items, listed, warnings = state.get("seen", {}), [], {}, []

    for t in data["reviewThreads"]["nodes"]:
        opener = (t["opener"]["nodes"] or [None])[0]
        last = (t["latest"]["nodes"] or [None])[-1]
        if (t["isResolved"] or not from_bot(opener) or not from_bot(last)
                or seen.get(t["id"]) == last["id"]):
            continue
        listed[t["id"]] = last["id"]
        items.append({"id": t["id"], "kind": "thread", "author": last["author"]["login"],
                      "path": t["path"], "line": t["line"], "outdated": t["isOutdated"],
                      "url": last["url"], "excerpt": excerpt(last["body"])})
    for key, kind_name in (("comments", "comment"), ("reviews", "review")):
        for c in data[key]["nodes"]:
            if (not from_bot(c) or c["isMinimized"] or not clean(c["body"])
                    or seen.get(c["id"]) == c["updatedAt"]):
                continue
            listed[c["id"]] = c["updatedAt"]
            items.append({"id": c["id"], "kind": kind_name, "author": c["author"]["login"],
                          "url": c["url"], "excerpt": excerpt(c["body"])})
    for key in ("reviewThreads", "comments", "reviews"):
        if data[key]["pageInfo"]["hasPreviousPage"]:
            warnings.append(f"Only the newest 100 {key} were checked.")

    blocked = state.get("blocked")
    if blocked and blocked["head"] != data["headRefOid"]:
        state.pop("blocked")
        blocked = None
    state["listed"] = listed
    pr.save(state)
    commits = data["commits"]["nodes"]
    rollup = commits and (commits[0]["commit"]["statusCheckRollup"] or {})
    contexts = (rollup or {}).get("contexts", {}).get("nodes", [])
    failing = sorted({c.get("name") or c.get("context") for c in contexts
                      if (c.get("conclusion") or c.get("state")) in FAILED})
    out = {"state": data["state"], "head": data["headRefOid"][:7], "busy": pr.busy(),
           "failing_checks": failing, "items": items, "warnings": warnings}
    if blocked:
        out["blocked"] = blocked["reason"]
    return out


def show(pr, ids):
    for i in ids:
        kind(i)
    pr.touch()
    out = []
    for node in pr.gql(SHOW_Q, allow_missing=True, ids=ids)["nodes"]:
        if not node:
            continue
        if node["__typename"] == "PullRequestReviewThread":
            comments = node["comments"]["nodes"]
            out.append({"id": node["id"], "kind": "thread", "resolved": node["isResolved"],
                        "outdated": node["isOutdated"], "path": node["path"], "line": node["line"],
                        "diff_hunk": comments[0]["diffHunk"] if comments else "",
                        "comments": [{"author": (c["author"] or {}).get("login"),
                                      "bot": from_bot(c), "url": c["url"], "body": clean(c["body"])}
                                     for c in comments]})
        else:
            out.append({"id": node["id"], "kind": kind(node["id"]),
                        "author": (node["author"] or {}).get("login"), "bot": from_bot(node),
                        "url": node["url"], "body": clean(node["body"])})
    return {"items": out, "deleted": sorted(set(ids) - {o["id"] for o in out})}


def mark_seen(pr, ids):
    pr.touch()
    state = pr.load()
    listed, seen = state.get("listed", {}), state.setdefault("seen", {})
    for i in ids:
        if i in listed:
            seen[i] = listed[i]
    pr.save(state)
    return {"seen": [i for i in ids if i in listed],
            "not_in_last_list": [i for i in ids if i not in listed]}


def reply(pr, item_id, body):
    body = body.strip()
    if not body:
        raise Fail("The reply is empty.", 2)
    outside_code = re.sub(r"```.*?```|`[^`\n]*`", "", body, flags=re.S)
    mentions = sorted(set(MENTION_RE.findall(outside_code)))
    if mentions:
        raise Fail(f"Remove {', '.join(mentions)} (or put it in backticks): an @mention "
                   "notifies people and wakes bots that act on mentions.", 2)
    pr.touch()
    pr.open_or_fail()
    body = f"**babysit-pr:** {body}"
    if kind(item_id) == "thread":
        result = pr.gql(REPLY_M, id=item_id, body=body)["addPullRequestReviewThreadReply"]
        url = (result or {}).get("comment", {}).get("url")
    else:
        target = (pr.gql(URL_Q, id=item_id)["node"] or {}).get("url")
        if not target:
            raise Fail(f"{item_id} is gone (deleted?), so there's nothing to reply to.", 2)
        pr_id = pr.gql(PR_ID_Q, **pr.repo_vars())["repository"]["pullRequest"]["id"]
        result = pr.gql(COMMENT_M, id=pr_id, body=f"Re: {target}\n\n{body}")["addComment"]
        url = (result or {}).get("commentEdge", {}).get("node", {}).get("url")
    if not url:
        raise Fail(f"GitHub didn't confirm the reply to {item_id}.")
    return {"replied": url}


def resolve(pr, item_id):
    if kind(item_id) != "thread":
        raise Fail("Only threads (PRRT_ ids) can be resolved. Use `hide` for comments and reviews.", 2)
    pr.touch()
    result = pr.gql(RESOLVE_M, id=item_id)["resolveReviewThread"]
    if not ((result or {}).get("thread") or {}).get("isResolved"):
        raise Fail(f"GitHub didn't confirm {item_id} as resolved.")
    return {"resolved": item_id}


def hide(pr, item_id):
    if kind(item_id) == "thread":
        raise Fail("Threads are resolved, not hidden. Use `resolve`.", 2)
    pr.touch()
    result = pr.gql(HIDE_M, id=item_id)["minimizeComment"]
    if not ((result or {}).get("minimizedComment") or {}).get("isMinimized"):
        raise Fail(f"GitHub didn't confirm {item_id} as hidden.")
    return {"hidden": item_id}


def main(argv=None):
    p = argparse.ArgumentParser(description="Plumbing for the babysit-pr skill.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("list", "claim", "sync", "push", "checks", "done"):
        sub.add_parser(name).add_argument("pr")
    s = sub.add_parser("start")
    s.add_argument("pr")
    s.add_argument("--worktree")
    s = sub.add_parser("stop")
    s.add_argument("pr")
    s.add_argument("--force", action="store_true")
    for name in ("show", "seen"):
        s = sub.add_parser(name)
        s.add_argument("pr")
        s.add_argument("ids", nargs="+")
    for name in ("resolve", "hide"):
        s = sub.add_parser(name)
        s.add_argument("pr")
        s.add_argument("id")
    r = sub.add_parser("reply")
    r.add_argument("pr")
    r.add_argument("id")
    r.add_argument("--body-file", required=True, help="path, or - for stdin")
    args = p.parse_args(argv)
    try:
        pr = PR(args.pr)
        if args.cmd == "start":
            out = start(pr, args.worktree)
        elif args.cmd == "stop":
            out = stop(pr, args.force)
        elif args.cmd == "reply":
            body = sys.stdin.read() if args.body_file == "-" else Path(args.body_file).read_text()
            out = reply(pr, args.id, body)
        elif args.cmd in ("show", "seen"):
            out = (show if args.cmd == "show" else mark_seen)(pr, args.ids)
        elif args.cmd in ("resolve", "hide"):
            out = (resolve if args.cmd == "resolve" else hide)(pr, args.id)
        else:
            out = {"list": list_items, "claim": claim, "sync": sync, "push": push,
                   "checks": checks, "done": done}[args.cmd](pr)
    except Fail as e:
        print(e, file=sys.stderr)
        return e.code
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
