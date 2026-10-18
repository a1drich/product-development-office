"""Local clones of the target repo: one main clone, plus a git worktree per issue."""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

from office.config import WORKSPACE
from office.gh import branch_name
from office.shell import CommandError, Result, run

# Worktrees share the clone's refs, so concurrent fetches race on git's ref locks.
# The office serializes its own git calls; agents may still run git in a worktree at
# the same moment, so lock contention is also retried.
LOCK_ERRORS = ("cannot lock ref", "index.lock", "Unable to create", "unable to update local ref")


class Workspace:
    def __init__(self, repo: str, root: Path = WORKSPACE):
        self.repo = repo
        name = repo.split("/")[-1]
        self.clone = root / name
        self.worktrees = root / f"{name}-worktrees"
        self.lock = threading.RLock()

    def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> Result:
        for attempt in range(4):
            with self.lock:
                res = run(["git", *args], cwd=cwd or self.clone, check=False)
            if res.ok or not any(e in res.stderr for e in LOCK_ERRORS):
                break
            time.sleep(2 * (attempt + 1))
        if check and not res.ok:
            raise CommandError(["git", *args], res)
        return res

    def ensure_clone(self) -> Path:
        if not (self.clone / ".git").exists():
            self.clone.parent.mkdir(parents=True, exist_ok=True)
            run(["gh", "repo", "clone", self.repo, str(self.clone)])
        else:
            self.git("fetch", "--prune", "origin")
        return self.clone

    def default_branch(self) -> str:
        res = self.git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
        return res.stdout.strip().removeprefix("origin/") if res.ok else "main"

    def update_default_branch(self) -> None:
        with self.lock:
            branch = self.default_branch()
            self.git("fetch", "origin")
            self.git("checkout", "-q", branch)
            self.git("reset", "-q", "--hard", f"origin/{branch}")

    def worktree(self, issue: int) -> Path:
        """A worktree on the issue's branch: reuses the remote branch if a PR already exists."""
        path = self.worktrees / f"issue-{issue}"
        branch = branch_name(issue)
        with self.lock:
            self.git("fetch", "origin")
            if path.exists():
                self.git("checkout", "-q", branch, cwd=path, check=False)
                self.git("pull", "-q", "--ff-only", cwd=path, check=False)
                return path
            self.worktrees.mkdir(parents=True, exist_ok=True)
            remote = self.git("rev-parse", "--verify", f"origin/{branch}", check=False)
            local = self.git("rev-parse", "--verify", branch, check=False)
            if local.ok:
                self.git("worktree", "add", str(path), branch)
            elif remote.ok:
                self.git("worktree", "add", "--track", "-b", branch, str(path), f"origin/{branch}")
            else:
                base = f"origin/{self.default_branch()}"
                self.git("worktree", "add", "-b", branch, str(path), base)
        return path

    def remove_worktree(self, issue: int) -> None:
        path = self.worktrees / f"issue-{issue}"
        with self.lock:
            if path.exists():
                self.git("worktree", "remove", "--force", str(path), check=False)
                shutil.rmtree(path, ignore_errors=True)
            self.git("worktree", "prune", check=False)
            self.git("branch", "-D", branch_name(issue), check=False)
