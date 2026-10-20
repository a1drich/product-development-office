"""Decides what to do next from the issues' labels. Pure logic, no I/O, so it is unit tested."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from office import labels as L
from office.gh import Issue

CLAIM_MARK = "<!-- office:claim -->"
FAILED_MARK = "<!-- office:failed -->"
# A review asking for changes or a failed test, sending the work back to an engineer.
BOUNCE_MARK = "<!-- office:bounced -->"
# Comments after which bounces count from zero again: a human has looked at the issue.
RESET_MARKS = ("<!-- office:blocked -->", "<!-- office:unblocked -->")
DEPENDS_MARK = re.compile(r"<!-- office:depends ([\d, ]+) -->")
# A release issue's comments record each deploy and rollback with the commit it was at.
RELEASE_MARK = re.compile(r"<!-- office:(deployed|rolled-back) ([0-9a-f]{7,40}) -->")
HEAD_MARK = re.compile(r"<!-- office:head ([0-9a-f]{7,40}) -->")

# Housekeeping kinds need no agent; the orchestrator does them directly.
HOUSEKEEPING = {"release", "close_done", "unwait", "break_cycle"}

ROLE_BY_KIND = {
    "triage": "pm",
    "resolve_blocker": "pm",
    "practices": "pm",
    "design": "designer",
    "implement": "engineer",
    "review": "reviewer",
    "test": "tester",
    "live_check": "tester",
}
# Release steps the orchestrator runs itself, off the loop thread: they run the target's
# verify and release commands, which can take minutes.
OFFICE_RUN = {"deploy", "rollback"}


@dataclass(frozen=True)
class Task:
    kind: str
    issue: int
    priority: int = 9
    repo: str = ""  # which repo's issue, when one office runs several

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


def bounces(issue: Issue) -> int:
    """Times the work went back to an engineer since a human last looked at the issue."""
    count = 0
    for c in reversed(issue.comments):
        if any(m in c.body for m in RESET_MARKS):
            break
        if BOUNCE_MARK in c.body:
            count += 1
    return count


def dependencies(issue: Issue) -> list[int]:
    """The issues the latest waiting comment says this one depends on."""
    for c in reversed(issue.comments):
        m = DEPENDS_MARK.search(c.body)
        if m:
            return [int(n) for n in re.findall(r"\d+", m.group(1))]
    return []


def waiting_graph(issues: list[Issue]) -> dict[int, set[int]]:
    """Which open issues each waiting issue waits for."""
    open_numbers = {i.number for i in issues}
    return {i.number: set(dependencies(i)) & open_numbers
            for i in issues if L.WAITING in i.labels}


def reachable(graph: dict[int, set[int]], start: int) -> set[int]:
    """Every issue `start` waits for, directly or through the issues it waits for."""
    seen: set[int] = set()
    todo = list(graph.get(start, ()))
    while todo:
        n = todo.pop()
        if n not in seen:
            seen.add(n)
            todo += graph.get(n, ())
    return seen


def circular(issues: list[Issue], number: int, deps: list[int]) -> list[int]:
    """The deps that already wait, directly or not, for `number`: waiting on them would
    leave both waiting forever."""
    graph = waiting_graph(issues)
    return [d for d in deps if d == number or number in reachable(graph, d)]


def cycle_of(issues: list[Issue], number: int) -> list[int]:
    """The waiting issues in a cycle with `number`, itself included, or [] if none."""
    graph = waiting_graph(issues)
    if number not in reachable(graph, number):
        return []
    return sorted(n for n in graph if n == number or (number in reachable(graph, n)
                                                       and n in reachable(graph, number)))


def cycle_breakers(issues: list[Issue]) -> set[int]:
    """For each cycle of waiting issues, the most urgent one, to release so work goes on."""
    by_number = {i.number: i for i in issues}
    breakers = set()
    for n in waiting_graph(issues):
        cycle = cycle_of(issues, n)
        if cycle:
            breakers.add(min(cycle, key=lambda m: (priority(by_number[m]), m)))
    return breakers


def deployed(issue: Issue) -> str | None:
    """The commit a release issue is live at: its latest deploy, unless a rollback
    followed it."""
    for c in reversed(issue.comments):
        m = RELEASE_MARK.search(c.body)
        if m:
            return m.group(2) if m.group(1) == "deployed" else None
    return None


def release_head(issue: Issue) -> str | None:
    """The default branch's commit when the release issue's list was last updated."""
    m = HEAD_MARK.search(issue.body)
    return m.group(1) if m else None


def release_task(issue: Issue) -> Task | None:
    """A release issue waits for the owner's approval label, then is deployed, checked
    live, and closed or (on approval) rolled back."""
    if L.ROLLBACK_APPROVED in issue.labels and deployed(issue):
        return Task("rollback", issue.number, 0)
    if deployed(issue):
        return Task("live_check", issue.number, 0) if issue.status == L.TESTING else None
    if L.RELEASE_APPROVED in issue.labels:
        return Task("deploy", issue.number, 0)
    return None


def task_for(
    issue: Issue, now: datetime, claim_ttl: timedelta, open_numbers: set[int] | None = None
) -> Task | None:
    if L.STATUS_ISSUE in issue.labels:
        return None
    if L.RELEASE in issue.labels:
        return release_task(issue)
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


def candidates(
    issues: list[Issue],
    running: dict[int, str],
    now: datetime,
    claim_ttl: timedelta,
    held: frozenset[str] = frozenset(),
    repo: str = "",
) -> list[Task]:
    """Every task one repo could start now, most urgent first, before any limits.

    `running` maps issue number -> role for this repo's agents already working. Task kinds
    in `held` are not started this pass.
    """
    open_numbers = {i.number for i in issues}
    found = []
    for issue in issues:
        if issue.number in running:
            continue
        task = task_for(issue, now, claim_ttl, open_numbers)
        if task is None or task.kind in held:
            continue
        found.append(Task(task.kind, task.issue, task.priority, repo))
    by_number = {i.number: i for i in issues}
    for n in cycle_breakers(issues) - set(running):
        found.append(Task("break_cycle", n, priority(by_number[n]), repo))
    return sorted(found, key=lambda t: (t.priority, t.issue))


def select(tasks: list[Task], busy: dict[str, int], limits: dict[str, int],
           paused: set[str]) -> list[Task]:
    """The tasks to start, taken in the order given, within each role's concurrency limit.
    `busy` counts the agents of each role already running, in every repo."""
    busy = dict(busy)
    chosen = []
    for task in tasks:
        role = task.role
        if role is None:
            chosen.append(task)
            continue
        if role in paused or busy.get(role, 0) >= limits.get(role, 1):
            continue
        busy[role] = busy.get(role, 0) + 1
        chosen.append(task)
    return chosen


def busy_roles(running: dict[int, str]) -> dict[str, int]:
    busy: dict[str, int] = {}
    for role in running.values():
        busy[role] = busy.get(role, 0) + 1
    return busy


def plan(
    issues: list[Issue],
    running: dict[int, str],
    limits: dict[str, int],
    paused: set[str],
    now: datetime,
    claim_ttl: timedelta,
    held: frozenset[str] = frozenset(),
) -> list[Task]:
    """Tasks to start now in one repo, most urgent first, within each role's limit."""
    return select(candidates(issues, running, now, claim_ttl, held), busy_roles(running),
                  limits, paused)


def actionable(issues: list[Issue], now: datetime, claim_ttl: timedelta) -> bool:
    open_numbers = {i.number for i in issues}
    return any(task_for(i, now, claim_ttl, open_numbers) for i in issues)


def blocks_section(body: str) -> list[int]:
    """Issue numbers listed under a blocker's "## Blocks" heading."""
    m = re.search(r"^## Blocks\s*$(.*?)(?=^## |^---|\Z)", body, re.M | re.S)
    return [int(n) for n in re.findall(r"#(\d+)", m.group(1))] if m else []
