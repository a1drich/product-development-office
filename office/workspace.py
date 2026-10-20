"""Local clones of the target repo: one main clone, plus a git worktree per issue."""

from __future__ import annotations

import os
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


def folder_name(repo: str) -> str:
    """`owner__repo`, so repos with the same name under different owners never collide."""
    owner, name = repo.split("/", 1)
    return f"{owner}__{name}"


class Workspace:
    def __init__(self, repo: str, root: Path = WORKSPACE):
        self.repo = repo
        self.root = root
        name = folder_name(repo)
        self.clone = root / name
        self.worktrees = root / f"{name}-worktrees"
        self.docs_log = root / f"{name}-mkdocs.log"
        self.pidfile = root / f"{name}.pid"
        # Shared by every office on the machine; each repo's leases are named after it.
        self.leases = root / "leases"
        self.lock = threading.RLock()

    @property
    def paths(self) -> list[Path]:
        """This repo's own local state. The shared leases folder isn't in it; its lease
        files are (see `own_leases`)."""
        legacy_leases = self.root / f"{folder_name(self.repo)}-leases"
        return [self.clone, self.worktrees, self.docs_log, self.pidfile, legacy_leases,
                *self.own_leases()]

    def own_leases(self) -> list[Path]:
        return sorted(self.leases.glob(f"{folder_name(self.repo)}.*.json"))

    def running_pid(self) -> int | None:
        """The pid of the office running on this repo, if one is."""
        try:
            pid = int(self.pidfile.read_text().strip())
            os.kill(pid, 0)
        except (FileNotFoundError, ValueError, ProcessLookupError):
            return None
        except PermissionError:
            pass  # alive, but owned by someone else
        return pid

    def repos_in_process(self, pid: int) -> list[str]:
        """Every repo the office process `pid` runs, read from the pidfiles."""
        repos = []
        for f in sorted(self.root.glob("*.pid")):
            try:
                if int(f.read_text().strip()) == pid:
                    owner, _, name = f.stem.partition("__")
                    repos.append(f"{owner}/{name}")
            except (OSError, ValueError):
                continue
        return repos

    def acquire_pidfile(self) -> None:
        pid = self.running_pid()
        if pid and pid != os.getpid():
            raise RuntimeError(f"an office is already running on {self.repo} (pid {pid}); "
                               f"stop it with `office stop {self.repo}`")
        self.pidfile.parent.mkdir(parents=True, exist_ok=True)
        self.pidfile.write_text(f"{os.getpid()}\n")

    def release_pidfile(self) -> None:
        if self.running_pid() == os.getpid():
            self.pidfile.unlink(missing_ok=True)

    def migrate_legacy(self) -> bool:
        """Moves a folder from the old `workspace/<repo>` layout to `<owner>__<repo>`, if
        its origin is this repo. Worktrees are moved too, and repaired, so work in them
        is kept."""
        legacy_name = self.repo.split("/", 1)[1]
        legacy = self.root / legacy_name
        if self.clone.exists() or not (legacy / ".git").exists():
            return False
        origin = run(["git", "remote", "get-url", "origin"], cwd=legacy, check=False).stdout
        if not origin.strip().removesuffix(".git").endswith(self.repo):
            return False
        from office.agents import leftover_pids

        legacy_trees = self.root / f"{legacy_name}-worktrees"
        busy = leftover_pids(legacy) | (leftover_pids(legacy_trees) if legacy_trees.exists()
                                        else set())
        if busy:
            raise RuntimeError(
                f"{legacy} is still in use (pids {', '.join(map(str, sorted(busy)))}); stop the "
                "office before it moves the folder to the new layout"
            )
        legacy.rename(self.clone)
        if legacy_trees.exists():
            legacy_trees.rename(self.worktrees)
            trees = [str(p) for p in self.worktrees.iterdir() if p.is_dir()]
            if trees:
                self.git("worktree", "repair", *trees, check=False)
        legacy_log = self.root / f"{legacy_name}-mkdocs.log"
        if legacy_log.exists():
            legacy_log.rename(self.docs_log)
        return True

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
        self.migrate_legacy()
        if not (self.clone / ".git").exists():
            self.clone.parent.mkdir(parents=True, exist_ok=True)
            run(["gh", "repo", "clone", self.repo, str(self.clone)])
        else:
            self.git("fetch", "--prune", "origin")
        return self.clone

    def default_branch(self) -> str:
        res = self.git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
        return res.stdout.strip().removeprefix("origin/") if res.ok else "main"

    def head(self) -> str:
        """The commit the main clone is at."""
        return self.git("rev-parse", "HEAD").stdout.strip()

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
