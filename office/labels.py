"""The label set that drives the office's state machine. See docs/WORKFLOW.md, "Labels"."""

from __future__ import annotations

from dataclasses import dataclass

TRIAGE = "status:triage"
DESIGN = "status:design"
READY = "status:ready"
IN_PROGRESS = "status:in-progress"
IN_REVIEW = "status:in-review"
TESTING = "status:testing"
DONE = "status:done"

BLOCKED = "blocked:human"
# Labels a repo may already use for owner-only work. The office treats them like
# blocked:human: it skips the issue until a human removes the label.
BLOCKED_ALIASES = {"blocked"}
BLOCKER = "office:blocker"
STATUS_ISSUE = "office:status"
PRACTICE = "office:practice"
WAITING = "office:waiting"

STATUSES = [TRIAGE, DESIGN, READY, IN_PROGRESS, IN_REVIEW, TESTING, DONE]


@dataclass(frozen=True)
class Label:
    name: str
    color: str
    description: str


LABELS = [
    Label(TRIAGE, "C5DEF5", "New or unscoped; the PM writes acceptance criteria"),
    Label(DESIGN, "D4C5F9", "Needs a design doc before engineering"),
    Label(READY, "0E8A16", "Fully specified; an engineer can pick it up"),
    Label(IN_PROGRESS, "FBCA04", "An engineer is working on it"),
    Label(IN_REVIEW, "1D76DB", "PR open, waiting for Codex review"),
    Label(TESTING, "5319E7", "PR approved, waiting for Codex testing"),
    Label(DONE, "0E8A16", "Verified locally and merged"),
    Label(BLOCKED, "B60205", "Waiting for a human decision"),
    Label(BLOCKER, "B60205", "A decision the office needs from a human"),
    Label(STATUS_ISSUE, "BFDADC", "The office's running status summary"),
    Label(WAITING, "EDEDED", "Waiting for other issues to close; requeued automatically"),
    Label(PRACTICE, "C2E0C6", "A suggested improvement to how the repo is built or maintained"),
    *(Label(f"priority:p{p}", "FBCA04", f"Priority {p}") for p in range(4)),
]
