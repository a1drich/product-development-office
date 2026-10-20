from datetime import UTC, datetime, timedelta

from test_orchestrator import FakeGitHub, FakeWorkspace

from office import floor as floor_module
from office import labels as L
from office import orchestrator
from office.agents import AgentResult
from office.config import Config
from office.floor import Floor
from office.gh import Issue
from office.orchestrator import Office, Shared
from office.planner import Task


def floor(tmp_path, repos, limits=None):
    """A floor over fake repos, {repo: [issues]}. Started tasks are recorded, not run."""
    cfg = Config()
    if limits:
        cfg.limits.update(limits)
    shared = Shared()
    offices, started = [], []
    for i, (repo, issues) in enumerate(repos.items()):
        root = tmp_path / str(i)
        (root / ".claude" / "skills" / "impeccable").mkdir(parents=True)
        gh = FakeGitHub(issues)
        gh.repo = repo
        office = Office(cfg, gh, FakeWorkspace(root), shared=shared)
        office.last_practices = datetime.now(UTC)  # no practices review due
        office.post_summary = lambda issues: None
        office.start = started.append
        offices.append(office)
    return Floor(cfg, offices, shared), offices, started


def ready(n, *labels):
    return Issue(n, f"issue {n}", "", {L.READY, *labels})


def test_limits_count_agents_in_every_repo(tmp_path):
    fl, (a, b), started = floor(tmp_path, {"acme/a": [ready(1)], "acme/b": [ready(2)]},
                                {"engineer": 1})
    a.running = {7: "engineer"}  # repo a's engineer holds the machine's only slot
    fl.cycle()
    assert started == []


def test_equally_urgent_work_takes_turns_between_repos(tmp_path):
    fl, _, started = floor(tmp_path, {"acme/a": [ready(1)], "acme/b": [ready(2)]},
                           {"engineer": 1})
    fl.cycle()
    fl.cycle()
    assert [t.repo for t in started] == ["acme/a", "acme/b"]


def test_more_urgent_work_goes_first_whichever_repo_it_is_in(tmp_path):
    fl, _, started = floor(tmp_path, {"acme/a": [ready(1, "priority:p2")],
                                      "acme/b": [ready(2, "priority:p0")]}, {"engineer": 1})
    fl.cycle()
    assert started == [Task("implement", 2, 0, "acme/b")]


def test_a_usage_limit_in_one_repo_pauses_the_role_in_every_repo(tmp_path):
    fl, (a, b), started = floor(tmp_path, {"acme/a": [ready(1)], "acme/b": [ready(2)]})
    a.accept(a.gh.issue(1), Task("implement", 1), AgentResult("engineer", None, "",
                                                              rate_limited=True), set())
    assert b.paused(datetime.now(UTC)) == {"engineer"}
    fl.cycle()
    assert started == []
    a.paused_until["engineer"] = datetime.now(UTC) - timedelta(seconds=1)
    fl.cycle()
    assert len(started) == 1


def test_each_repos_docs_site_gets_its_own_port(tmp_path, monkeypatch):
    fl, offices, _ = floor(tmp_path, {"acme/a": [], "acme/b": [], "acme/c": []})
    for o in offices[:2]:
        (o.ws.clone / "mkdocs.yml").write_text("site_name: x")
    monkeypatch.setattr(orchestrator.ports, "in_use", lambda p: p == 8788)
    fl.assign_docs_ports()
    # The third has no site yet, but a merge may add one: it gets a port of its own too.
    assert [o.docs.port for o in offices] == [8787, 8789, 8790]


def test_start_sweeps_each_repos_leftover_containers_and_only_its_own(tmp_path, monkeypatch):
    fl, offices, _ = floor(tmp_path, {"acme/a": [], "acme/b": []})
    swept = []
    monkeypatch.setattr(orchestrator.containers, "remove",
                        lambda prefix, allowed=None: swept.append(prefix) or [])
    monkeypatch.setattr(floor_module.ghshim, "install", lambda: None)
    monkeypatch.setattr(fl, "loop", lambda exit_when_idle: None)
    for o in offices:
        o.dbs.drop = lambda prefix=None: []
    fl.serve(exit_when_idle=True)
    assert swept == [orchestrator.databases.repo_prefix("acme/a"),
                     orchestrator.databases.repo_prefix("acme/b")]
