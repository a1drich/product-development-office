"""`office plan`: what the office would do next, read from GitHub only.

Strictly read-only: it never touches the local clone, labels or issues, so it is safe to
run while an office is running.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from office import labels as L
from office import planner
from office.gh import Issue

NEXT = {
    "triage": "PM triages it",
    "resolve_blocker": "PM applies your answer",
    "design": "Designer designs it",
    "implement": "an engineer builds it",
    "review": "Codex reviews its PR",
    "test": "Codex tests and merges its PR",
    "release": "its stale claim is released",
    "close_done": "it is closed",
    "unwait": "it is requeued (dependencies closed)",
    "deploy": "the office releases it (you approved)",
    "rollback": "the office rolls it back (you approved)",
    "live_check": "Codex checks the live site",
}


@dataclass
class Row:
    issue: Issue
    status: str
    priority: str
    next: str
    order: tuple  # sort key: actionable first, then the office's own order


def describe(issues: list[Issue], now: datetime, claim_ttl: timedelta) -> list[Row]:
    open_numbers = {i.number for i in issues}
    rows = []
    for issue in issues:
        if L.STATUS_ISSUE in issue.labels:
            continue
        task = planner.task_for(issue, now, claim_ttl, open_numbers)
        p = planner.priority(issue)
        status = issue.status.removeprefix("status:") if issue.status else "new"
        if task:
            nxt, rank = NEXT[task.kind], 0
        elif L.WAITING in issue.labels:
            deps = [f"#{n}" for n in planner.dependencies(issue) if n in open_numbers]
            nxt, rank = f"waits for {', '.join(deps) or 'its dependencies'}", 1
        elif issue.status == L.IN_PROGRESS:
            claimed = planner.last_claim(issue)
            age = f" ({int((now - claimed).total_seconds() // 60)} min)" if claimed else ""
            nxt, rank = f"an engineer is working on it{age}", 1
        elif L.RELEASE in issue.labels:
            nxt = (f"live check failed: add `{L.ROLLBACK_APPROVED}`, or close it to keep it"
                   if planner.deployed(issue) else f"waits for you to add `{L.RELEASE_APPROVED}`")
            rank = 2
        elif issue.is_blocker:
            nxt, rank = "waits for your answer", 2
        elif L.PRACTICE in issue.labels and issue.blocked:
            nxt, rank = "waits for your approval", 2
        elif issue.blocked:
            nxt, rank = "blocked: waits for you", 2
        else:
            nxt, rank = "nothing", 3
        rows.append(Row(issue, status, f"p{p}" if p < 9 else "-", nxt, (rank, p, issue.number)))
    return sorted(rows, key=lambda r: r.order)


def render_leases(leases: list[tuple[str, int, str]]) -> str:
    """The ports running agents hold, from `ports.Leases.table`."""
    if not leases:
        return "Ports: no agent holds any."
    return "Ports held by running agents:\n" + "\n".join(
        f"  #{issue}: {ports}" if name == "ports" else f"  #{issue}: {name} ({ports})"
        for name, issue, ports in leases)


def render(rows: list[Row], limits: dict[str, int]) -> str:
    if not rows:
        return "No open issues."
    width = max(len(r.issue.title) for r in rows)
    width = min(max(width, 5), 60)
    lines = [f"{'#':>5}  {'Title':<{width}}  {'Status':<11}  {'Pri':<3}  Next",
             f"{'':->5}  {'':-<{width}}  {'':-<11}  {'':-<3}  {'':-<30}"]
    for r in rows:
        title = r.issue.title if len(r.issue.title) <= width else r.issue.title[: width - 1] + "…"
        lines.append(f"{r.issue.number:>5}  {title:<{width}}  {r.status:<11}  {r.priority:<3}  "
                     f"{r.next}")
    counts: dict[str, int] = {}
    for r in rows:
        bucket = ("actionable", "in progress / waiting on other work",
                  "waiting on you", "idle")[r.order[0]]
        counts[bucket] = counts.get(bucket, 0) + 1
    lines.append("")
    lines.append(", ".join(f"{n} {k}" for k, n in counts.items()))
    lines.append("Concurrency: " + ", ".join(f"{role} {n}" for role, n in limits.items()))
    lines.append("Only engineers post claims, so a running office may already be doing a "
                 "triage, design, review or test step shown here.")
    return "\n".join(lines)
