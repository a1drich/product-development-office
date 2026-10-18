from datetime import UTC, datetime

import pytest

from office import labels as L
from office import orchestrator
from office.agents import AgentResult, Verdict
from office.config import Config
from office.gh import Comment, Issue
from office.planner import FAILED_MARK, Task


class FakeGitHub:
    repo = "acme/app"

    def __init__(self, issues):
        self.issues = {i.number: i for i in issues}
        self.prs = {}
        self.merged = []
        self.checks = (True, "")

    def open_issues(self):
        return [i for i in self.issues.values() if i.state == "OPEN"]

    def issue(self, n):
        return self.issues[n]

    def create_issue(self, title, body, labels):
        n = max(self.issues) + 1
        self.issues[n] = Issue(n, title, body, set(labels))
        return n

    def comment(self, n, body):
        self.issues[n].comments.append(Comment("office", body, datetime.now(UTC)))

    def edit_labels(self, n, add=(), remove=()):
        self.issues[n].labels = (self.issues[n].labels | set(add)) - set(remove)

    def set_status(self, issue, status):
        stale = {s for s in L.STATUSES if s != status}
        issue.labels = (issue.labels - stale) | {status}
        self.issues[issue.number].labels = issue.labels

    def assign_self(self, n):
        pass

    def close_issue(self, n, comment=None):
        self.issues[n].state = "CLOSED"

    def pr_for_issue(self, n):
        return self.prs.get(n)

    def pr_checks_passing(self, pr):
        return self.checks

    def merge_pr(self, pr):
        self.merged.append(pr)

    def find_issue_by_title(self, title, label=None):
        return None

    def edit_body(self, n, body):
        self.issues[n].body = body


class FakeWorkspace:
    def __init__(self, tmp_path):
        self.clone = tmp_path

    def default_branch(self):
        return "main"

    def update_default_branch(self):
        pass

    def worktree(self, n):
        return self.clone

    def remove_worktree(self, n):
        pass


@pytest.fixture
def make_office(tmp_path, monkeypatch):
    def make(issues, verdicts):
        gh = FakeGitHub(issues)
        office = orchestrator.Office(Config(), gh, FakeWorkspace(tmp_path))
        queue = list(verdicts)

        def fake_run_agent(role, prompt, cwd, cfg):
            item = queue.pop(0)
            if isinstance(item, AgentResult):
                return item
            return AgentResult(role, item, "")

        monkeypatch.setattr(orchestrator, "run_agent", fake_run_agent)
        return office, gh

    return make


def blocked_verdict():
    return Verdict("blocked", "needs a call", blocker={
        "title": "Guest checkout?", "decision": "Allow guest checkout in v1?",
        "context": "ctx", "options": ["Yes", "No"], "recommendation": "No",
    })


def test_triage_ready_moves_to_ready_and_files_follow_ups(make_office):
    office, gh = make_office(
        [Issue(1, "Add login", "", set())],
        [Verdict("ready", "scoped it", new_issues=[{"title": "Part 2", "body": "rest"}])],
    )
    office.execute(Task("triage", 1))
    assert L.READY in gh.issues[1].labels
    assert gh.issues[2].title == "Part 2" and L.TRIAGE in gh.issues[2].labels


def test_blocked_files_a_templated_blocker(make_office):
    office, gh = make_office([Issue(1, "Checkout", "", {L.TRIAGE})], [blocked_verdict()])
    office.execute(Task("triage", 1))
    blocker = gh.issues[2]
    assert {L.BLOCKER, L.BLOCKED} <= blocker.labels
    for section in ["## Decision needed", "## Context", "## Options", "## Recommendation",
                    "## Blocks\n#1"]:
        assert section in blocker.body
    assert L.BLOCKED in gh.issues[1].labels
    assert L.TRIAGE in gh.issues[1].labels  # keeps its place in the flow


def test_engineer_blocked_releases_the_claim(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.READY})], [blocked_verdict()])
    office.execute(Task("implement", 1))
    assert L.READY in gh.issues[1].labels and L.BLOCKED in gh.issues[1].labels


def test_engineer_opened_pr_goes_to_review(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.READY})], [Verdict("opened", "done", pr=5)])
    gh.prs[1] = {"number": 5}
    office.execute(Task("implement", 1))
    assert L.IN_REVIEW in gh.issues[1].labels


def test_engineer_claims_but_no_pr_counts_as_failure(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.READY})], [Verdict("opened", "done")])
    office.execute(Task("implement", 1))
    assert L.READY in gh.issues[1].labels
    assert FAILED_MARK in gh.issues[1].comments[-1].body


def test_review_changes_go_back_to_ready(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.IN_REVIEW})], [Verdict("changes", "bug")])
    gh.prs[1] = {"number": 5}
    office.execute(Task("review", 1))
    assert L.READY in gh.issues[1].labels


def test_tester_pass_merges_and_closes(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.TESTING})], [Verdict("pass", "all good")])
    gh.prs[1] = {"number": 5}
    office.execute(Task("test", 1))
    assert gh.merged == [5]
    assert L.DONE in gh.issues[1].labels and gh.issues[1].state == "CLOSED"


def test_tester_pass_but_ci_failing_does_not_merge(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.TESTING})], [Verdict("pass", "ok")])
    gh.prs[1] = {"number": 5}
    gh.checks = (False, "lint  fail  1m")
    office.execute(Task("test", 1))
    assert gh.merged == []
    assert L.READY in gh.issues[1].labels


def test_resolved_blocker_unblocks_and_closes(make_office):
    blocker = Issue(2, "Decision: x", "## Decision needed\nq\n\n## Blocks\n#1\n\n---\n",
                    {L.BLOCKER})
    office, gh = make_office([Issue(1, "x", "", {L.READY, L.BLOCKED}), blocker],
                             [Verdict("resolved", "applied")])
    office.execute(Task("resolve_blocker", 2))
    assert L.BLOCKED not in gh.issues[1].labels
    assert gh.issues[2].state == "CLOSED"


def test_three_failures_file_a_blocker(make_office):
    office, gh = make_office(
        [Issue(1, "x", "", {L.DESIGN})],
        [AgentResult("designer", None, "", error="boom")] * 3,
    )
    for _ in range(3):
        office.execute(Task("design", 1))
    blockers = [i for i in gh.issues.values() if L.BLOCKER in i.labels]
    assert len(blockers) == 1 and "keeps failing" in blockers[0].title
    assert L.BLOCKED in gh.issues[1].labels


def test_rate_limit_pauses_the_role(make_office):
    office, gh = make_office(
        [Issue(1, "x", "", {L.READY})],
        [AgentResult("engineer", None, "", rate_limited=True)],
    )
    office.execute(Task("implement", 1))
    assert "engineer" in office.paused(datetime.now(UTC))
    assert L.READY in gh.issues[1].labels


def test_unexpected_outcome_is_a_failure(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.TRIAGE})], [Verdict("merge-it", "nope")])
    office.execute(Task("triage", 1))
    assert FAILED_MARK in gh.issues[1].comments[-1].body
