from datetime import UTC, datetime

import pytest

from office import labels as L
from office import orchestrator, readiness, shell
from office.agents import AgentResult, Verdict
from office.config import Config
from office.gh import Comment, Issue
from office.planner import FAILED_MARK, Task
from office.shell import Result


class FakeGitHub:
    repo = "acme/app"

    def __init__(self, issues):
        self.issues = {i.number: i for i in issues}
        self.prs = {}
        self.merged = []
        self.checks = (True, "")
        self.files = {}
        self.conflicting = set()
        self.pr_comments = []
        self.label_actors = {}  # (issue, label) -> login; the owner by default
        self.permissions = {"owner": "admin"}

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

    def pr_conflicts(self, pr):
        return pr in self.conflicting

    def pr_files(self, pr):
        return "abc123", self.files.get(pr, [])

    def pr_comment(self, pr, body):
        self.pr_comments.append((pr, body))

    def merge_pr(self, pr):
        self.merged.append(pr)

    def find_issue_by_title(self, title, label=None):
        for i in self.open_issues():
            if i.title == title and (label is None or label in i.labels):
                return i.number
        return None

    def open_issue_titles(self):
        return {i.number: i.title for i in self.open_issues()}

    def edit_body(self, n, body):
        self.issues[n].body = body

    def labelled_issues(self, label, state="open", limit=10):
        found = [i for i in self.issues.values() if label in i.labels and i.state == state.upper()]
        return sorted(found, key=lambda i: -i.number)[:limit]

    def label_added_by(self, n, label):
        return self.label_actors.get((n, label), "owner")

    def permission(self, login):
        return self.permissions.get(login, "write")


class FakeWorkspace:
    def __init__(self, tmp_path):
        self.clone = tmp_path
        self.docs_log = tmp_path / "mkdocs.log"
        self.leases = tmp_path / "leases"
        self.head_sha = "abc1234"

    def head(self):
        return self.head_sha

    def git(self, *args, cwd=None, check=True):
        return Result(0, "", "")

    def default_branch(self):
        return "main"

    def update_default_branch(self):
        pass

    def worktree(self, n):
        return self.clone

    def remove_worktree(self, n):
        pass

    def acquire_pidfile(self):
        pass

    def release_pidfile(self):
        pass


@pytest.fixture
def make_office(tmp_path, monkeypatch):
    def make(issues, verdicts, impeccable=True):
        if impeccable:
            (tmp_path / ".claude" / "skills" / "impeccable").mkdir(parents=True, exist_ok=True)
        gh = FakeGitHub(issues)
        office = orchestrator.Office(Config(), gh, FakeWorkspace(tmp_path))
        # No real port probing or lsof in these tests; tests/test_ports.py covers them.
        office.leases.probe = lambda port: False
        monkeypatch.setattr(orchestrator.ports, "stop_listeners", lambda held: [])
        queue = list(verdicts)

        def fake_run_agent(role, prompt, cwd, cfg, exclusive=False, env=None):
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


def test_practice_suggestions_wait_for_approval_and_are_not_duplicated(make_office):
    practice = {"title": "Practice: run ruff in CI", "body": "ci.yml skips lint"}
    office, gh = make_office(
        [Issue(1, "x", "", {L.TRIAGE})],
        [Verdict("ready", "ok", new_issues=[practice, {"title": "Bug: y", "body": "b"}]),
         Verdict("ready", "ok", new_issues=[practice])],
    )
    office.execute(Task("triage", 1))
    filed = {i.title: i for i in gh.issues.values() if i.number != 1}
    assert {L.PRACTICE, L.BLOCKED, L.TRIAGE} <= filed["Practice: run ruff in CI"].labels
    assert L.BLOCKED not in filed["Bug: y"].labels
    gh.issues[1].labels = {L.TRIAGE}
    office.execute(Task("triage", 1))
    assert sum(i.title == practice["title"] for i in gh.issues.values()) == 1


def test_follow_ups_matching_an_open_title_loosely_are_not_filed(make_office):
    follow_ups = [{"title": "Practice: add a CI workflow?", "body": "b"},
                  {"title": "Add CI workflows for deploys", "body": "b"}]
    office, gh = make_office(
        [Issue(1, "x", "", {L.TRIAGE}), Issue(2, "Add CI workflow", "", {L.TRIAGE})],
        [Verdict("ready", "ok", new_issues=follow_ups)],
    )
    office.execute(Task("triage", 1))
    titles = [i.title for i in gh.issues.values()]
    assert "Practice: add a CI workflow?" not in titles
    assert "Add CI workflows for deploys" in titles  # different words: a different issue


def test_prompts_list_the_other_open_issues(make_office):
    office, gh = make_office([Issue(1, "Add login", "", {L.TRIAGE}),
                              Issue(2, "Add MkDocs site", "", {L.READY}),
                              Issue(3, orchestrator.STATUS_TITLE, "", {L.STATUS_ISSUE})], [])
    listed = office.values(gh.issues[1])["open_issues"]
    assert listed == "- #2 Add MkDocs site"


def test_normalize_title():
    assert orchestrator.normalize_title("Practice:  Add CI!") == orchestrator.normalize_title(
        "add ci")


def test_practices_review_is_scheduled_when_due_and_capped(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.READY})], [])
    now = datetime.now(UTC)
    task = office.practices_task(gh.open_issues(), now)
    assert task and task.kind == "practices"
    status = gh.issues[task.issue]
    assert L.STATUS_ISSUE in status.labels

    office.last_practices = now
    assert office.practices_task(gh.open_issues(), now) is None

    office.last_practices = None
    for n in range(3):
        gh.create_issue(f"Practice: {n}", "", [L.PRACTICE, L.BLOCKED])
    assert office.practices_task(gh.open_issues(), now) is None


def test_practices_review_files_suggestions_and_records_the_run(make_office):
    office, gh = make_office(
        [Issue(1, "Office status", "", {L.STATUS_ISSUE})],
        [Verdict("done", "reviewed", new_issues=[{"title": "Practice: x", "body": "why"}])],
    )
    office.execute(Task("practices", 1))
    assert any(i.title == "Practice: x" for i in gh.issues.values())
    assert "<!-- office:practices -->" in gh.issues[1].comments[-1].body


def test_waiting_parks_the_issue_until_dependencies_close(make_office):
    from datetime import timedelta

    from office.planner import plan

    office, gh = make_office(
        [Issue(4, "form", "", {L.IN_REVIEW}), Issue(6, "cta", "", {L.READY})],
        [Verdict("waiting", "needs #4's form", depends_on=[4])],
    )
    office.execute(Task("implement", 6))
    assert {L.READY, L.WAITING} <= gh.issues[6].labels
    assert not any(L.BLOCKER in i.labels for i in gh.issues.values())

    def kinds():
        now = datetime.now(UTC)
        return [(t.kind, t.issue) for t in plan(gh.open_issues(), {}, Config().limits, set(),
                                                 now, timedelta(hours=2))]

    assert ("implement", 6) not in kinds() and ("unwait", 6) not in kinds()
    gh.issues[4].state = "CLOSED"
    assert ("unwait", 6) in kinds()
    office.housekeeping(Task("unwait", 6))
    assert L.WAITING not in gh.issues[6].labels
    assert ("implement", 6) in kinds()


def test_waiting_without_dependencies_is_a_failure(make_office):
    office, gh = make_office([Issue(6, "x", "", {L.READY})], [Verdict("waiting", "?")])
    office.execute(Task("implement", 6))
    assert L.WAITING not in gh.issues[6].labels
    assert FAILED_MARK in gh.issues[6].comments[-1].body


def test_merge_posts_changed_screens_on_the_pr_and_status_issue(make_office):
    office, gh = make_office([Issue(1, "Empty state", "", {L.TESTING})], [Verdict("pass", "ok")])
    gh.prs[1] = {"number": 5}
    gh.files[5] = ["templates/home.html", "docs/manual/screenshots/home-empty-mobile.png"]
    office.execute(Task("test", 1))
    pr, body = gh.pr_comments[0]
    url = "https://github.com/acme/app/blob/abc123/docs/manual/screenshots/home-empty-mobile.png"
    assert pr == 5 and f"{url}?raw=true" in body
    status = next(i for i in gh.issues.values() if L.STATUS_ISSUE in i.labels)
    assert "Screens changed by PR #5" in status.comments[-1].body
    assert gh.merged == [5]


def test_merge_without_screens_posts_nothing(make_office):
    office, gh = make_office([Issue(1, "API", "", {L.TESTING})], [Verdict("pass", "ok")])
    gh.prs[1] = {"number": 5}
    gh.files[5] = ["notes/views.py"]
    office.execute(Task("test", 1))
    assert gh.pr_comments == [] and gh.merged == [5]


def test_restart_releases_leftover_claims(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.IN_PROGRESS}), Issue(2, "y", "", {L.READY})], [])
    office.recover_claims()
    assert L.READY in gh.issues[1].labels and L.IN_PROGRESS not in gh.issues[1].labels
    assert gh.issues[2].comments == []


def test_bootstrap_files_the_impeccable_setup_issue_once(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.TRIAGE})], [], impeccable=False)
    office.bootstrap()
    office.bootstrap()
    filed = [i for i in gh.issues.values() if i.title == readiness.IMPECCABLE_TITLE]
    assert len(filed) == 1
    assert filed[0].labels == {L.READY, "priority:p0"}
    assert "npx skills add pbakaus/impeccable" in filed[0].body


def test_bootstrap_skips_a_repo_that_has_impeccable(make_office, tmp_path):
    (tmp_path / ".agents" / "skills" / "impeccable").mkdir(parents=True)
    office, gh = make_office([Issue(1, "x", "", {L.TRIAGE})], [], impeccable=False)
    office.bootstrap()
    assert list(gh.issues) == [1]


def test_bootstrap_in_a_dry_run_files_nothing(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.TRIAGE})], [], impeccable=False)
    office.dry_run = True
    office.bootstrap()
    assert list(gh.issues) == [1]


def test_design_waits_while_the_impeccable_setup_issue_is_open(make_office, monkeypatch):
    office, gh = make_office([Issue(1, "x", "", {L.DESIGN}),
                              Issue(2, readiness.IMPECCABLE_TITLE, "", {L.READY})], [])
    started = []
    monkeypatch.setattr(office, "start", started.append)
    monkeypatch.setattr(office, "practices_task", lambda *a: None)
    office.cycle()
    assert [(t.kind, t.issue) for t in started] == [("implement", 2)]
    gh.close_issue(2)
    started.clear()
    office.cycle()
    assert [(t.kind, t.issue) for t in started] == [("design", 1)]


def test_dry_run_without_a_status_issue_plans_without_touching_github(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.READY})], [])
    office.dry_run = True
    tasks = office.cycle()
    assert ("implement", 1) in [(t.kind, t.issue) for t in tasks]
    assert list(gh.issues) == [1]


class FakeDatabases:
    def __init__(self):
        self.dropped = []

    def drop(self, prefix=None):
        self.dropped.append(prefix)
        return []


@pytest.mark.parametrize("crash", [False, True])
def test_worktree_agents_get_a_prefix_and_their_databases_are_dropped(make_office, monkeypatch,
                                                                      crash):
    office, gh = make_office([Issue(1, "x", "", {L.READY})], [])
    office.dbs = FakeDatabases()
    seen = {}

    def engineer(role, prompt, cwd, cfg, exclusive=False, env=None):
        seen.update(env or {})
        if crash:
            raise RuntimeError("agent crashed")
        return AgentResult(role, Verdict("failed", "nope"), "")

    monkeypatch.setattr(orchestrator, "run_agent", engineer)
    office.safely(Task("implement", 1), office.execute)
    prefix = orchestrator.databases.prefix_for("acme/app", 1)
    assert seen["OFFICE_DB_PREFIX"] == prefix
    assert seen["OFFICE_PORTS"] == "40000-40009" and seen["OFFICE_PORT_BASE"] == "40000"
    assert office.leases.table() == []  # released after the run, even a crashed one
    assert (seen["OFFICE_AGENT_ROLE"], seen["OFFICE_ISSUE"]) == ("engineer", "1")
    if office.real_gh:  # the signing gh wrapper comes first on the agent's PATH
        assert seen["PATH"].startswith(str(orchestrator.ghshim.BIN))
    assert office.dbs.dropped == [prefix]


def test_agents_in_the_main_clone_are_identified_too(make_office, monkeypatch):
    office, gh = make_office([Issue(1, "Add login", "", set())], [])
    seen = {}

    def pm(role, prompt, cwd, cfg, exclusive=False, env=None):
        seen.update(env or {})
        return AgentResult(role, Verdict("ready", "scoped"), "")

    monkeypatch.setattr(orchestrator, "run_agent", pm)
    office.execute(Task("triage", 1))
    assert (seen["OFFICE_AGENT_ROLE"], seen["OFFICE_ISSUE"]) == ("pm", "1")


def test_the_prompt_names_the_leased_ports_and_cleanup_stops_their_servers(make_office,
                                                                           monkeypatch):
    office, gh = make_office([Issue(1, "x", "", {L.READY})], [])
    prompts, stopped = [], []

    def engineer(role, prompt, cwd, cfg, exclusive=False, env=None):
        prompts.append(prompt)
        return AgentResult(role, Verdict("failed", "nope"), "")

    monkeypatch.setattr(orchestrator, "run_agent", engineer)
    monkeypatch.setattr(orchestrator.ports, "stop_listeners",
                        lambda held: stopped.extend(held) or [])
    office.execute(Task("implement", 1))
    assert "Your run has its own ports: 40000-40009" in prompts[0]
    assert "{{ports}}" not in prompts[0]
    assert stopped == list(range(40000, 40010))


def test_main_clone_steps_get_no_ports(make_office, monkeypatch):
    office, gh = make_office([Issue(1, "Add login", "", set())], [])
    prompts = []

    def pm(role, prompt, cwd, cfg, exclusive=False, env=None):
        prompts.append(prompt)
        return AgentResult(role, Verdict("ready", "scoped"), "")

    monkeypatch.setattr(orchestrator, "run_agent", pm)
    office.execute(Task("triage", 1))
    assert "Your run has its own ports: none: this step doesn't run the app." in prompts[0]


def test_start_sweeps_databases_left_by_earlier_runs(make_office):
    office, gh = make_office([], [])
    office.dbs = FakeDatabases()
    office.sweep_databases()
    assert office.dbs.dropped == [None]  # None: everything the office made for this repo


def test_runs_interrupted_by_shutdown_are_not_failures(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.DESIGN})],
                             [AgentResult("designer", None, "", error="interrupted")])
    office.stopping.set()
    office.execute(Task("design", 1))
    assert not any(FAILED_MARK in c.body for c in gh.issues[1].comments)


@pytest.mark.parametrize("kind,status", [("review", L.IN_REVIEW), ("test", L.TESTING)])
def test_conflicting_pr_goes_back_without_running_an_agent(make_office, kind, status):
    office, gh = make_office([Issue(1, "x", "", {status})], [])  # no agent results queued
    gh.prs[1] = {"number": 5}
    gh.conflicting.add(5)
    office.execute(Task(kind, 1))
    assert L.READY in gh.issues[1].labels
    assert "conflicts with `main`" in gh.issues[1].comments[-1].body
    assert gh.merged == []


def test_conflict_appearing_during_testing_goes_back_without_a_failure(make_office,
                                                                      monkeypatch):
    office, gh = make_office([Issue(1, "x", "", {L.TESTING})], [])
    gh.prs[1] = {"number": 5}

    def tester(role, prompt, cwd, cfg, exclusive=False, env=None):
        gh.conflicting.add(5)  # another PR merged while this one was tested
        return AgentResult(role, Verdict("pass", "all good"), "")

    monkeypatch.setattr(orchestrator, "run_agent", tester)
    office.execute(Task("test", 1))
    assert gh.merged == []
    assert L.READY in gh.issues[1].labels
    assert not any(FAILED_MARK in c.body for c in gh.issues[1].comments)


def test_merge_rejected_for_conflicts_goes_back_without_a_failure(make_office):
    office, gh = make_office([Issue(1, "x", "", {L.TESTING})], [Verdict("pass", "all good")])
    gh.prs[1] = {"number": 5}

    def merge_pr(pr):  # GitHub hadn't computed mergeability, so the pre-check passed
        raise shell.CommandError(["gh", "pr", "merge"], shell.Result(
            1, "", "GraphQL: Pull Request has merge conflicts (mergePullRequest)"))

    gh.merge_pr = merge_pr
    office.execute(Task("test", 1))
    assert L.READY in gh.issues[1].labels
    assert "conflicts with `main`" in gh.issues[1].comments[-1].body
    assert not any(FAILED_MARK in c.body for c in gh.issues[1].comments)


def run_with_signals(office, gh, signals, agent_seconds):
    """Runs the real loop with an agent that takes `agent_seconds`, sending SIGINT to
    ourselves `signals` times once the agent is busy."""
    import os
    import signal
    import threading
    import time

    from office import shell

    def agent(role, prompt, cwd, cfg, exclusive=False, env=None):
        res = shell.run(["sleep", str(agent_seconds)], check=False)
        gh.prs[1] = {"number": 5}
        if res.ok:
            return AgentResult(role, Verdict("opened", "built it"), "")
        return AgentResult(role, None, "", error="killed")

    orchestrator.run_agent = agent

    def send():
        time.sleep(1)
        for _ in range(signals):
            os.kill(os.getpid(), signal.SIGINT)
            time.sleep(0.3)

    threading.Thread(target=send, daemon=True).start()
    started = time.monotonic()
    office.run()
    return time.monotonic() - started


def test_ctrl_c_drains_running_agents_and_starts_nothing_new(make_office, monkeypatch):
    office, gh = make_office([Issue(1, "x", "", {L.READY}), Issue(2, "y", "", {L.READY})], [])
    office.cfg.poll_seconds = 1
    office.cfg.limits["engineer"] = 1
    monkeypatch.setattr(orchestrator, "run_agent", orchestrator.run_agent)
    elapsed = run_with_signals(office, gh, signals=1, agent_seconds=3)
    assert elapsed >= 3  # waited for the running agent
    assert L.IN_REVIEW in gh.issues[1].labels  # its verdict was applied
    assert L.READY in gh.issues[2].labels  # nothing new started while draining


def test_second_ctrl_c_stops_running_agents_now(make_office, monkeypatch):
    office, gh = make_office([Issue(1, "x", "", {L.READY})], [])
    office.cfg.poll_seconds = 1
    monkeypatch.setattr(orchestrator, "run_agent", orchestrator.run_agent)
    elapsed = run_with_signals(office, gh, signals=2, agent_seconds=30)
    assert elapsed < 15  # the 30s agent was ended
    assert not any(FAILED_MARK in c.body for c in gh.issues[1].comments)  # not a failure
    assert L.IN_PROGRESS in gh.issues[1].labels  # released at the next start


# --- releases -------------------------------------------------------------------------

MAKEFILE = "verify:\n\techo\nrelease:\n\techo\nrollback:\n\techo\n"


@pytest.fixture
def releasing(make_office, tmp_path):
    """An office on a repo with release and rollback commands. Commands it runs are
    recorded, and fail when their name is in `failing`."""
    def make(issues, verdicts=(), failing=()):
        (tmp_path / "Makefile").write_text(MAKEFILE)
        office, gh = make_office(issues, verdicts)
        office.ran = []

        def command(args, cwd, env):
            office.ran.append(" ".join(args))
            bad = any(name in args for name in failing)
            return Result(1 if bad else 0, "output", "")

        office.command = command
        return office, gh
    return make


def release_issue(n=9, *labels, head="abc1234", comments=()):
    body = orchestrator.release_body(["- #1 Contact form (PR #5)"], head, "make verify",
                                     "make release", "make rollback")
    return Issue(n, "Release", body, {L.RELEASE, *labels}, comments=list(comments))


def deployed_comment(sha="abc1234"):
    return Comment("office", f"Released.\n<!-- office:deployed {sha} -->", datetime.now(UTC))


def test_a_user_visible_merge_opens_one_release_issue_that_later_merges_join(releasing):
    office, gh = releasing([Issue(1, "API tweak", "", {L.TESTING}),
                            Issue(2, "Contact form", "", {L.TESTING}),
                            Issue(3, "Refactor", "", {L.TESTING})],
                           [Verdict("pass", "ok")] * 3)
    for n, pr, files in ((1, 11, ["api/views.py"]), (2, 12, ["docs/manual/README.md"]),
                         (3, 13, ["src/util.js"])):
        gh.prs[n] = {"number": pr}
        gh.files[pr] = files
        office.execute(Task("test", n))
        if n == 1:
            assert gh.labelled_issues(L.RELEASE) == []  # nothing users can see yet
    [release] = gh.labelled_issues(L.RELEASE)
    assert {L.RELEASE, L.BLOCKED} <= release.labels
    assert orchestrator.release_changes(release.body) == [
        "- #2 Contact form (PR #12)", "- #3 Refactor (PR #13)"]
    assert "<!-- office:head abc1234 -->" in release.body


def test_merges_open_no_release_issue_in_a_repo_without_a_release_command(make_office):
    office, gh = make_office([Issue(1, "Contact form", "", {L.TESTING})], [Verdict("pass", "ok")])
    gh.prs[1] = {"number": 5}
    gh.files[5] = ["docs/manual/README.md"]
    office.execute(Task("test", 1))
    assert gh.merged == [5] and gh.labelled_issues(L.RELEASE) == []


def test_an_approved_release_is_verified_released_then_checked_live(releasing):
    office, gh = releasing([release_issue(9, L.BLOCKED, L.RELEASE_APPROVED)])
    office.execute(Task("deploy", 9))
    assert office.ran == ["make verify", "make release"]
    issue = gh.issues[9]
    assert L.TESTING in issue.labels and not issue.labels & {L.BLOCKED, L.RELEASE_APPROVED}
    assert "<!-- office:deployed abc1234 -->" in issue.comments[-1].body
    assert orchestrator.planner.task_for(issue, datetime.now(UTC), orchestrator.timedelta(1)
                                         ).kind == "live_check"


@pytest.mark.parametrize("setup, expected", [
    (lambda office, gh: setattr(office.ws, "head_sha", "def5678"), "moved"),
    (lambda office, gh: gh.label_actors.update({(9, L.RELEASE_APPROVED): "bot"}), "isn't a repo"),
])
def test_a_release_is_refused_when_main_moved_or_an_admin_did_not_approve(releasing, setup,
                                                                          expected):
    office, gh = releasing([release_issue(9, L.BLOCKED, L.RELEASE_APPROVED)])
    setup(office, gh)
    office.execute(Task("deploy", 9))
    assert office.ran == []
    issue = gh.issues[9]
    assert L.RELEASE_APPROVED not in issue.labels and L.BLOCKED in issue.labels
    assert expected in issue.comments[-1].body


def test_a_failing_verify_releases_nothing(releasing):
    office, gh = releasing([release_issue(9, L.BLOCKED, L.RELEASE_APPROVED)], failing=["verify"])
    office.execute(Task("deploy", 9))
    assert office.ran == ["make verify"]
    assert "nothing was released" in gh.issues[9].comments[-1].body
    assert L.RELEASE_APPROVED not in gh.issues[9].labels and L.BLOCKED in gh.issues[9].labels


def test_a_passing_live_check_closes_the_release(releasing):
    office, gh = releasing([release_issue(9, L.TESTING, comments=[deployed_comment()])],
                           [Verdict("pass", "all pages load")])
    office.execute(Task("live_check", 9))
    assert gh.issues[9].state == "CLOSED" and L.DONE in gh.issues[9].labels


def test_a_failing_live_check_asks_the_owner_and_rolls_back_only_on_approval(releasing):
    old = release_issue(3, comments=[deployed_comment("0000aaa")])
    old.state = "CLOSED"
    office, gh = releasing([old, release_issue(9, L.TESTING, comments=[deployed_comment()])],
                           [Verdict("fail", "the contact form 500s")])
    office.execute(Task("live_check", 9))
    issue = gh.issues[9]
    assert L.BLOCKED in issue.labels and L.TESTING not in issue.labels
    assert L.ROLLBACK_APPROVED in issue.comments[-1].body
    assert office.ran == []

    gh.edit_labels(9, add=[L.ROLLBACK_APPROVED])
    office.execute(Task("rollback", 9))
    assert office.ran == ["make rollback REF=0000aaa"]
    assert L.ROLLBACK_APPROVED not in issue.labels and L.BLOCKED in issue.labels
    # Rolled back, it is a pending release again: the same changes, waiting for approval.
    assert orchestrator.planner.deployed(issue) is None


def test_no_rollback_without_an_earlier_release_to_go_back_to(releasing):
    office, gh = releasing([release_issue(9, L.BLOCKED, L.ROLLBACK_APPROVED,
                                          comments=[deployed_comment()])])
    office.execute(Task("rollback", 9))
    assert office.ran == []
    assert "no earlier release" in gh.issues[9].comments[-1].body
    assert L.ROLLBACK_APPROVED not in gh.issues[9].labels


def test_a_practice_overlapping_an_open_one_is_added_to_it_not_filed(make_office):
    office, gh = make_office([
        Issue(4, "Practice: Move agent guidance to AGENTS.md and add an MkDocs docs site with "
                 "product brief, decision log and user manual", "", {L.PRACTICE, L.BLOCKED}),
        Issue(1, "x", "", {L.READY})], [])
    office.file_follow_up(gh.issues[1], "Practice: add AGENTS.md with a verify command, and a "
                                        "docs site", "evidence")
    assert len(gh.issues) == 2
    assert "Also suggested while working on #1" in gh.issues[4].comments[-1].body
    office.file_follow_up(gh.issues[1], "Practice: Pin Node in CI", "evidence")
    assert len(gh.issues) == 3


def test_no_practice_is_filed_once_the_cap_is_reached(make_office):
    office, gh = make_office([Issue(n, f"Practice: topic {w}", "", {L.PRACTICE, L.BLOCKED})
                              for n, w in ((2, "alpha"), (3, "beta"), (4, "gamma"))]
                             + [Issue(1, "x", "", {L.READY})], [])
    office.file_follow_up(gh.issues[1], "Practice: Pin Node in CI", "evidence")
    assert len(gh.issues) == 4
    office.file_follow_up(gh.issues[1], "Bug: the footer overlaps on mobile", "evidence")
    assert len(gh.issues) == 5  # bugs aren't capped


def test_same_topic():
    assert not orchestrator.same_topic(
        "Practice: Add `npm run verify` (lint + build + route smoke test) and run it in CI",
        "Practice: Give each route its own title, meta description and canonical URL")
    assert not orchestrator.same_topic("Fix login error on mobile", "Fix login button on desktop")
