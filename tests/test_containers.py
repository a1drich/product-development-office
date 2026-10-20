import json

import pytest

from office import containers
from office.containers import owned, project_for, published_ports, remove
from office.databases import prefix_for, repo_prefix
from office.shell import Result

PREFIX = prefix_for("acme/app", 1)
PROJECT = project_for("acme/app", 1)


class FakeDocker:
    """A stand-in `docker`: containers as name -> (compose project, published ports)."""

    def __init__(self, containers=None, networks=None, volumes=None, in_use=()):
        self.containers = containers or {}
        self.networks = networks or {}
        self.volumes = volumes or {}
        self.in_use = set(in_use)  # networks and volumes a kept container still uses
        self.removed = []

    def __call__(self, args, check=True, timeout=None, **kw):
        assert args[0] == "docker"
        cmd = args[1:]
        if cmd[:2] == ["container", "ls"]:
            rows = [f"{n}\t{p}" for n, (p, _) in self.containers.items()]
        elif cmd[1:2] == ["ls"]:
            rows = [f"{n}\t{p}" for n, p in getattr(self, cmd[0] + "s").items()]
        elif cmd[:2] == ["container", "inspect"]:
            return Result(0, json.dumps([
                {"Name": "/" + n, "HostConfig": {"PortBindings": {
                    "5432/tcp": [{"HostIp": "", "HostPort": str(port)} for port in ports]}}}
                for n in cmd[2:] for _, ports in [self.containers[n]]]), "")
        elif cmd[:2] == ["rm", "-f"]:
            self.removed += cmd[3:]
            rows = cmd[3:]
        elif cmd[1:2] == ["rm"]:
            if cmd[2] in self.in_use:
                return Result(1, "", "in use")
            self.removed.append(cmd[2])
            rows = [cmd[2]]
        else:
            raise AssertionError(cmd)
        return Result(0, "\n".join(rows), "")


@pytest.fixture
def docker(monkeypatch):
    def make(**kw):
        fake = FakeDocker(**kw)
        monkeypatch.setattr(containers, "run", fake)
        return fake

    return make


def test_the_compose_project_is_the_issue_prefix():
    assert PROJECT + "_" == PREFIX


def test_an_issue_owns_its_project_and_prefixed_names_only():
    assert owned(PREFIX, "anything-db-1", PROJECT)
    assert owned(PREFIX, PREFIX + "redis", "")
    assert not owned(PREFIX, "lyv_db", "lyv")
    assert not owned(PREFIX, "x", project_for("acme/app", 12))  # i1 never owns i12
    assert not owned(PREFIX, project_for("acme/app", 12) + "_redis", "")
    assert owned(repo_prefix("acme/app"), "x", project_for("acme/app", 12))
    assert not owned(repo_prefix("acme/app"), "x", project_for("acme/web", 1))


def test_removes_the_issues_containers_networks_and_volumes(docker):
    fake = docker(containers={"app-db-1": (PROJECT, []), PREFIX + "redis": ("", []),
                              "lyv_db": ("lyv", [5433])},
                  networks={PROJECT + "_default": PROJECT, "lyv_default": "lyv"},
                  volumes={PROJECT + "_pgdata": PROJECT, "lyv_pgdata": "lyv"})
    removed = remove(PREFIX, set(range(40000, 40010)))
    assert sorted(removed) == sorted(["app-db-1", PREFIX + "redis", PROJECT + "_default",
                                      PROJECT + "_pgdata"])
    assert not {"lyv_db", "lyv_default", "lyv_pgdata"} & set(fake.removed)


def test_keeps_a_container_publishing_a_port_outside_the_lease(docker):
    fake = docker(containers={"app-web-1": (PROJECT, [40001]), "app-db-1": (PROJECT, [5433])},
                  volumes={PROJECT + "_pgdata": PROJECT}, in_use={PROJECT + "_pgdata"})
    assert remove(PREFIX, set(range(40000, 40010))) == ["app-web-1"]
    assert "app-db-1" not in fake.removed


def test_the_sweep_removes_kept_containers_too(docker):
    docker(containers={"app-db-1": (PROJECT, [5433])})
    assert remove(repo_prefix("acme/app")) == ["app-db-1"]


def test_never_touches_anything_outside_the_office_prefix(docker):
    docker()
    with pytest.raises(ValueError):
        remove("lyv_")


def test_without_docker_there_is_nothing_to_remove(monkeypatch):
    monkeypatch.setattr(containers, "run",
                        lambda *a, **k: Result(127, "", "docker: command not found"))
    assert remove(PREFIX, set()) == []


def test_remove_never_raises(monkeypatch):
    monkeypatch.setattr(containers, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("daemon gone")))
    assert remove(PREFIX, set()) == []


def test_published_ports_ignore_unbound_and_random_ports():
    c = {"HostConfig": {"PortBindings": {"80/tcp": [{"HostPort": ""}], "443/tcp": None,
                                         "5432/tcp": [{"HostPort": "5433"}]}}}
    assert published_ports(c) == {5433}
    assert published_ports({}) == set()
