"""Signatures on everything the office posts to GitHub.

The office acts through the owner's own `gh` login, so GitHub shows its comments as the
owner's. Each comment, PR and issue it posts ends with a visible line naming the role,
and a hidden marker tools can match. The marker deliberately doesn't start with
`<!-- office:`, which the planner reserves for the orchestrator's state marks.
"""

from __future__ import annotations

MARK = "<!-- office-agent"
WHO = {
    "office": "Office",
    "pm": "PM (Claude)",
    "designer": "Designer (Claude)",
    "engineer": "Engineer (Claude)",
    "reviewer": "Reviewer (Codex)",
    "tester": "Tester (Codex)",
}


def footer(role: str, issue: int | str | None = None) -> str:
    name = WHO.get(role, role)
    where = f" issue={issue}" if issue else ""
    return (f"\n\n<sub>🤖 {name} · product development office</sub>\n"
            f"{MARK} role={role}{where} -->")


def sign(body: str, role: str, issue: int | str | None = None) -> str:
    """The body with a signature, unless it already has one."""
    if MARK in body:
        return body
    return body.rstrip() + footer(role, issue)


def is_signed(body: str) -> bool:
    return MARK in body
