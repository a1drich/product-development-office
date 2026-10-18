"""Local clones of the target repo: one main clone, plus a git worktree per issue."""

from __future__ import annotations

import shutil
from pathlib import Path

from office.config import WORKSPACE
from office.gh import branch_name
from office.shell import run


class Workspace:
    def __init__(self, repo: str, root: Path = WORKSPACE):
        self.repo = repo
        name = repo.split("/")[-1]
        self.clone = root / name
        self.worktrees = root / f"{name}-worktrees"

    def ensure_clone(self) -> Path:
        if not (self.clone / ".git").exists():
            self.clone.parent.mkdir(parents=True, exist_ok=True)
            run(["gh", "repo", "clone", self.repo, str(self.clone)])
        else:
            run(["git", "fetch", "--prune", "origin"], cwd=self.clone)
        return self.clone

    def default_branch(self) -> str:
        res = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=self.clone,
                  check=False)
        return res.stdout.strip().removeprefix("origin/") if res.ok else "main"

    def update_default_branch(self) -> None:
        branch = self.default_branch()
        run(["git", "fetch", "origin"], cwd=self.clone)
        run(["git", "checkout", "-q", branch], cwd=self.clone)
        run(["git", "reset", "-q", "--hard", f"origin/{branch}"], cwd=self.clone)

    def worktree(self, issue: int) -> Path:
        """A worktree on the issue's branch: reuses the remote branch if a PR already exists."""
        path = self.worktrees / f"issue-{issue}"
        branch = branch_name(issue)
        run(["git", "fetch", "origin"], cwd=self.clone)
        if path.exists():
            run(["git", "checkout", "-q", branch], cwd=path, check=False)
            run(["git", "pull", "-q", "--ff-only"], cwd=path, check=False)
            return path
        self.worktrees.mkdir(parents=True, exist_ok=True)
        remote = run(["git", "rev-parse", "--verify", f"origin/{branch}"], cwd=self.clone,
                     check=False)
        local = run(["git", "rev-parse", "--verify", branch], cwd=self.clone, check=False)
        if local.ok:
            run(["git", "worktree", "add", str(path), branch], cwd=self.clone)
        elif remote.ok:
            run(["git", "worktree", "add", "--track", "-b", branch, str(path), f"origin/{branch}"],
                cwd=self.clone)
        else:
            base = f"origin/{self.default_branch()}"
            run(["git", "worktree", "add", "-b", branch, str(path), base], cwd=self.clone)
        return path

    def remove_worktree(self, issue: int) -> None:
        path = self.worktrees / f"issue-{issue}"
        if path.exists():
            run(["git", "worktree", "remove", "--force", str(path)], cwd=self.clone, check=False)
            shutil.rmtree(path, ignore_errors=True)
        run(["git", "worktree", "prune"], cwd=self.clone, check=False)
        run(["git", "branch", "-D", branch_name(issue)], cwd=self.clone, check=False)
