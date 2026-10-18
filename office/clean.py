"""`office clean`: remove a project's local state, and optionally the office's traces on GitHub."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from office import labels as L
from office.agents import leftover_pids
from office.config import Config
from office.gh import GitHub
from office.workspace import Workspace


@dataclass
class GitHubPlan:
    labels: list[str] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    kept_branches: list[str] = field(default_factory=list)  # have an open PR
    status_issue: int | None = None

    @property
    def empty(self) -> bool:
        return not (self.labels or self.branches or self.status_issue)


def running_in(ws: Workspace) -> set[int]:
    """Processes still working in this project's folders: the office, agents, servers."""
    pids: set[int] = set()
    for path in (ws.clone, ws.worktrees):
        if path.exists():
            pids |= leftover_pids(path)
    return pids


def clean_local(ws: Workspace, cfg: Config) -> list[str]:
    removed = []
    for path in ws.paths:
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(str(path))
        elif path.exists():
            path.unlink()
            removed.append(str(path))
    if cfg.repo == ws.repo:
        cfg.repo = None
        cfg.save()
        removed.append("saved repo in .office/config.json (other settings kept)")
    return removed


def plan_github(gh: GitHub) -> GitHubPlan:
    office_labels = {lb.name for lb in L.LABELS}
    open_heads = gh.open_pr_branches()
    branches = gh.office_branches()
    return GitHubPlan(
        labels=sorted(office_labels & gh.label_names()),
        branches=[b for b in branches if b not in open_heads],
        kept_branches=[b for b in branches if b in open_heads],
        status_issue=gh.find_issue_by_title("Office status", L.STATUS_ISSUE),
    )


def clean_github(gh: GitHub, plan: GitHubPlan) -> None:
    for name in plan.labels:
        gh.delete_label(name)
    for branch in plan.branches:
        gh.delete_branch(branch)
    if plan.status_issue:
        gh.close_issue(plan.status_issue, "The office was removed from this repo.")
