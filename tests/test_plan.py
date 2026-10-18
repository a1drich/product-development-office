from datetime import UTC, datetime, timedelta

from office import labels as L
from office.gh import Comment, Issue
from office.plan import describe, render
from office.planner import CLAIM_MARK

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def issue(n, *labels, comments=()):
    return Issue(n, f"issue {n}", "", set(labels), comments=list(comments))


def test_describe_orders_and_explains_each_issue():
    rows = describe([
        issue(1, L.READY, "priority:p2"),
        issue(2, L.READY, "priority:p0"),
        issue(3, L.READY, L.WAITING,
              comments=[Comment("o", "<!-- office:depends 1 -->", NOW)]),
        issue(4, L.IN_PROGRESS, comments=[Comment("o", CLAIM_MARK, NOW - timedelta(minutes=5))]),
        issue(5, L.BLOCKER, L.BLOCKED),
        issue(6, L.TRIAGE, L.PRACTICE, L.BLOCKED),
        issue(7),
        issue(8, L.STATUS_ISSUE),
    ], NOW, timedelta(hours=2))
    by = {r.issue.number: r.next for r in rows}
    assert [r.issue.number for r in rows][:3] == [2, 1, 7]  # actionable first, by priority
    assert by[3] == "waits for #1"
    assert by[4] == "an engineer is working on it (5 min)"
    assert by[5] == "waits for your answer"
    assert by[6] == "waits for your approval"
    assert by[7] == "PM triages it"
    assert 8 not in by
    text = render(rows, {"engineer": 2})
    assert "3 actionable" in text and "engineer 2" in text
