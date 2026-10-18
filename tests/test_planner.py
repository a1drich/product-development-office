from datetime import UTC, datetime, timedelta

from office import labels as L
from office.gh import Comment, Issue
from office.planner import (
    CLAIM_MARK,
    FAILED_MARK,
    blocks_section,
    failures,
    plan,
    task_for,
)

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
TTL = timedelta(minutes=120)
LIMITS = {"pm": 1, "designer": 1, "engineer": 2, "reviewer": 1, "tester": 1}


def issue(n, *labels, comments=()):
    return Issue(n, f"issue {n}", "", set(labels), comments=list(comments))


def comment(body, minutes_ago=0):
    return Comment("office", body, NOW - timedelta(minutes=minutes_ago))


def kind(i):
    t = task_for(i, NOW, TTL)
    return t.kind if t else None


def test_status_maps_to_role():
    assert kind(issue(1)) == "triage"
    assert kind(issue(1, L.TRIAGE)) == "triage"
    assert kind(issue(1, L.DESIGN)) == "design"
    assert kind(issue(1, L.READY)) == "implement"
    assert kind(issue(1, L.IN_REVIEW)) == "review"
    assert kind(issue(1, L.TESTING)) == "test"
    assert kind(issue(1, L.DONE)) == "close_done"


def test_blocked_and_status_issues_are_skipped():
    assert kind(issue(1, L.READY, L.BLOCKED)) is None
    assert kind(issue(1, L.STATUS_ISSUE)) is None
    assert kind(issue(1, L.BLOCKER, L.BLOCKED)) is None


def test_answered_blocker_goes_to_pm():
    assert kind(issue(1, L.BLOCKER)) == "resolve_blocker"


def test_fresh_claim_is_left_alone_and_stale_claim_released():
    fresh = issue(1, L.IN_PROGRESS, comments=[comment(CLAIM_MARK, minutes_ago=10)])
    stale = issue(2, L.IN_PROGRESS, comments=[comment(CLAIM_MARK, minutes_ago=500)])
    unclaimed = issue(3, L.IN_PROGRESS)
    assert kind(fresh) is None
    assert kind(stale) == "release"
    assert kind(unclaimed) == "release"


def test_plan_respects_limits_priority_and_running():
    issues = [
        issue(1, L.READY),
        issue(2, L.READY, "priority:p0"),
        issue(3, L.READY),
        issue(4, L.TRIAGE),
        issue(5, L.TRIAGE),
        issue(6, L.IN_REVIEW),
    ]
    tasks = plan(issues, running={6: "reviewer"}, limits=LIMITS, paused=set(), now=NOW,
                 claim_ttl=TTL)
    started = [(t.kind, t.issue) for t in tasks]
    # Two engineer slots: the p0 issue first, then the lowest number.
    assert ("implement", 2) in started and ("implement", 1) in started
    assert ("implement", 3) not in started
    # One PM slot.
    assert [t for t in started if t[0] == "triage"] == [("triage", 4)]
    # Already running.
    assert ("review", 6) not in started


def test_paused_roles_get_no_work_but_housekeeping_still_runs():
    issues = [issue(1, L.READY), issue(2, L.DONE)]
    tasks = plan(issues, running={}, limits=LIMITS, paused={"engineer"}, now=NOW, claim_ttl=TTL)
    assert [(t.kind, t.issue) for t in tasks] == [("close_done", 2)]


def test_held_kinds_are_not_started():
    issues = [issue(1, L.DESIGN, "priority:p0"), issue(2, L.READY)]
    tasks = plan(issues, running={}, limits=LIMITS, paused=set(), now=NOW, claim_ttl=TTL,
                 held=frozenset({"design"}))
    assert [(t.kind, t.issue) for t in tasks] == [("implement", 2)]


def test_failures_count_since_last_progress():
    i = issue(1, L.READY, comments=[
        comment("<!-- office:advance -->"),
        comment(CLAIM_MARK),
        comment(FAILED_MARK),
        comment(CLAIM_MARK),
        comment(FAILED_MARK),
    ])
    assert failures(i) == 2
    i.comments.append(comment("Blocked on #9 <!-- office:blocked -->"))
    assert failures(i) == 0


def test_blocks_section():
    body = "## Decision needed\nx\n\n## Blocks\n#42, #43 and #44\n\n---\nfooter #99"
    assert blocks_section(body) == [42, 43, 44]
    assert blocks_section("no section") == []


def test_repo_blocked_label_is_respected():
    assert kind(issue(1, "blocked")) is None
    assert kind(issue(1, "blocked", L.READY)) is None


def test_repo_priority_labels():
    from office.planner import priority

    assert priority(issue(1, "P0")) == 0
    assert priority(issue(1, "priority:p2")) == 2
    assert priority(issue(1)) == 9


def test_every_agent_task_kind_has_a_role():
    from office.planner import ROLE_BY_KIND, Task

    for kind in ["triage", "resolve_blocker", "practices", "design", "implement", "review", "test"]:
        assert Task(kind, 1).role in {"pm", "designer", "engineer", "reviewer", "tester"}
    assert set(ROLE_BY_KIND) >= {"practices"}
