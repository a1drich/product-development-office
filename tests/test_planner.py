from datetime import UTC, datetime, timedelta

from office import labels as L
from office.gh import Comment, Issue
from office.planner import (
    BOUNCE_MARK,
    CLAIM_MARK,
    FAILED_MARK,
    blocks_section,
    bounces,
    candidates,
    circular,
    cycle_breakers,
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


def test_a_release_issue_waits_for_approval_then_deploys_checks_and_rolls_back():
    pending = issue(1, L.RELEASE, L.BLOCKED)
    assert kind(pending) is None
    assert kind(issue(1, L.RELEASE, L.BLOCKED, L.RELEASE_APPROVED)) == "deploy"
    live = [comment("Released.\n<!-- office:deployed abc1234 -->")]
    assert kind(issue(1, L.RELEASE, L.TESTING, comments=live)) == "live_check"
    # A failed live check waits for the owner: roll back, or close to keep it.
    assert kind(issue(1, L.RELEASE, L.BLOCKED, comments=live)) is None
    assert kind(issue(1, L.RELEASE, L.BLOCKED, L.ROLLBACK_APPROVED, comments=live)) == "rollback"
    # Approving the release again on a live one does nothing; rolled back, it's pending again.
    assert kind(issue(1, L.RELEASE, L.RELEASE_APPROVED, comments=live)) is None
    back = [*live, comment("Rolled back.\n<!-- office:rolled-back 0000aaa -->")]
    assert kind(issue(1, L.RELEASE, L.BLOCKED, L.RELEASE_APPROVED, comments=back)) == "deploy"


def waits(n, *deps, labels=()):
    return issue(n, L.WAITING, *labels,
                 comments=[comment(f"<!-- office:depends {','.join(map(str, deps))} -->")])


def test_a_wait_that_would_close_a_cycle_is_spotted():
    issues = [waits(3, 8), issue(8, L.IN_PROGRESS), waits(9, 3)]
    assert circular(issues, 8, [3]) == [3]  # 3 already waits for 8
    assert circular(issues, 8, [9]) == [9]  # 9 waits for 3, which waits for 8
    assert circular(issues, 8, [5]) == []


def test_issues_waiting_on_each_other_are_released_most_urgent_first():
    issues = [waits(3, 8), waits(8, 3, labels=["priority:p0"]), waits(4, 3)]
    assert cycle_breakers(issues) == {8}  # 4 waits for the cycle but isn't in it
    found = candidates(issues, {}, NOW, TTL, repo="acme/app")
    assert [(t.kind, t.issue) for t in found] == [("break_cycle", 8)]
    assert candidates(issues, {8: "pm"}, NOW, TTL) == []  # not while it's being worked on
    assert cycle_breakers([waits(3, 8), issue(8, L.READY)]) == set()


def test_bounces_count_since_a_human_last_looked():
    bounced = comment(f"Testing failed.\n{BOUNCE_MARK}")
    assert bounces(issue(1, comments=[bounced, bounced])) == 2
    reset = comment("Unblocked by #9.\n<!-- office:unblocked -->")
    assert bounces(issue(1, comments=[bounced, bounced, reset, bounced])) == 1
