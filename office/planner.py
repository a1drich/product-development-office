"""Decides what to do next from the issues' labels. Pure logic, no I/O, so it is unit tested."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from office import labels as L
from office.gh import Issue

CLAIM_MARK = "<!-- office:claim -->"
FAILED_MARK = "<!-- office:failed -->"
DEPENDS_MARK = re.compile(r"<!-- office:depends ([\d, ]+) -->")

# Housekeeping kinds need no agent; the orchestrator does them directly.
HOUSEKEEPING = {"release", "close_done", "unwait"}

ROLE_BY_KIND = {
    "triage": "pm",
    "resolve_blocker": "pm",
    "practices": "pm",
    "design": "designer",
    "implement": "engineer",
    "review": "reviewer",
    "test": "tester",
}


@dataclass(frozen=True)
class Task:
    kind: str
    issue: int
    priority: int = 9

    @property
    def role(self) -> str | None:
        return ROLE_BY_KIND.get(self.kind)


def priority(issue: Issue) -> int:
    for lb in issue.labels:
        # The office's priority:pN, or a repo's own P0..P3.
        m = re.fullmatch(r"(?:priority:)?p(\d)", lb, re.I)
        if m:
            return int(m.group(1))
    return 9


def last_claim(issue: Issue) -> datetime | None:
    times = [c.created_at for c in issue.comments if CLAIM_MARK in c.body]
    return max(times) if times else None


def failures(issue: Issue) -> int:
    """Failed agent runs since the issue's status last moved forward."""
    count = 0
    for c in reversed(issue.comments):
        if FAILED_MARK in c.body:
            count += 1
        elif CLAIM_MARK in c.body:
            continue
        elif "<!-- office:" in c.body:
            break
    return count


def dependencies(issue: Issue) -> list[int]:
    """The issues the latest waiting comment says this one depends on."""
    for c in reversed(issue.comments):
        m = DEPENDS_MARK.search(c.body)
        if m:
            return [int(n) for n in re.findall(r"\d+", m.group(1))]
    return []


def task_for(
    issue: Issue, now: datetime, claim_ttl: timedelta, open_numbers: set[int] | None = None
) -> Task | None:
    if L.STATUS_ISSUE in issue.labels:
        return None
    if L.WAITING in issue.labels:
        if open_numbers is not None and not set(dependencies(issue)) & open_numbers:
            return Task("unwait", issue.number, priority(issue))
        return None
    p = priority(issue)
    if issue.is_blocker:
        return None if issue.blocked else Task("resolve_blocker", issue.number, p)
    if issue.blocked:
        return None
    status = issue.status
    if status in (None, L.TRIAGE):
        return Task("triage", issue.number, p)
    if status == L.DESIGN:
        return Task("design", issue.number, p)
    if status == L.READY:
        return Task("implement", issue.number, p)
    if status == L.IN_PROGRESS:
        claimed = last_claim(issue)
        if claimed is None or now - claimed > claim_ttl:
            return Task("release", issue.number, p)
        return None
    if status == L.IN_REVIEW:
        return Task("review", issue.number, p)
    if status == L.TESTING:
        return Task("test", issue.number, p)
    if status == L.DONE:
        return Task("close_done", issue.number, p)
    return None


def plan(
    issues: list[Issue],
    running: dict[int, str],
    limits: dict[str, int],
    paused: set[str],
    now: datetime,
    claim_ttl: timedelta,
    held: frozenset[str] = frozenset(),
) -> list[Task]:
    """Tasks to start now, most urgent first, within each role's concurrency limit.

    `running` maps issue number -> role for agents already working. Task kinds in `held`
    are not started this pass.
    """
    busy: dict[str, int] = {}
    for role in running.values():
        busy[role] = busy.get(role, 0) + 1

    open_numbers = {i.number for i in issues}
    candidates = []
    for issue in issues:
        if issue.number in running:
            continue
        task = task_for(issue, now, claim_ttl, open_numbers)
        if task is None or task.kind in held:
            continue
        candidates.append(task)

    candidates.sort(key=lambda t: (t.priority, t.issue))
    chosen = []
    for task in candidates:
        role = task.role
        if role is None:
            chosen.append(task)
            continue
        if role in paused or busy.get(role, 0) >= limits.get(role, 1):
            continue
        busy[role] = busy.get(role, 0) + 1
        chosen.append(task)
    return chosen


def actionable(issues: list[Issue], now: datetime, claim_ttl: timedelta) -> bool:
    open_numbers = {i.number for i in issues}
    return any(task_for(i, now, claim_ttl, open_numbers) for i in issues)


def blocks_section(body: str) -> list[int]:
    """Issue numbers listed under a blocker's "## Blocks" heading."""
    m = re.search(r"^## Blocks\s*$(.*?)(?=^## |^---|\Z)", body, re.M | re.S)
    return [int(n) for n in re.findall(r"#(\d+)", m.group(1))] if m else []
