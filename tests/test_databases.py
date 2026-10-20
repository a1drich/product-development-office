import json

import pytest

from office import databases
from office.databases import Databases, compose_postgres, from_url, prefix_for, repo_prefix
from office.shell import Result

COMPOSE = {"services": {
    "redis": {"image": "redis:7"},
    "postgres": {"image": "postgres:16",
                 "environment": {"POSTGRES_USER": "app", "POSTGRES_PASSWORD": "pw"},
                 "ports": [{"target": 5432, "published": "5433"}]},
}}


def fake_compose(monkeypatch, tmp_path, config):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    monkeypatch.setattr(databases, "run", lambda *a, **k: Result(0, json.dumps(config), ""))


def test_prefixes_are_per_repo_and_per_issue():
    assert prefix_for("acme/app", 12).startswith(repo_prefix("acme/app"))
    assert prefix_for("acme/app", 12).endswith("_i12_")
    assert repo_prefix("acme/app") != repo_prefix("acme/web")
    assert repo_prefix("Acme/App") == repo_prefix("acme/app")


def test_reads_postgres_from_the_compose_config(monkeypatch, tmp_path):
    fake_compose(monkeypatch, tmp_path, COMPOSE)
    s = compose_postgres(tmp_path)
    assert (s.host, s.port, s.user, s.password, s.dbname) == ("127.0.0.1", 5433, "app", "pw",
                                                              "app")


def test_no_compose_file_or_no_published_port_means_no_cleanup(monkeypatch, tmp_path):
    assert compose_postgres(tmp_path) is None
    unpublished = {"services": {"db": {"image": "postgres:16"}}}
    fake_compose(monkeypatch, tmp_path, unpublished)
    assert compose_postgres(tmp_path) is None
    assert Databases(tmp_path, "acme/app").drop() == []


def test_never_touches_names_outside_the_office_prefix(tmp_path):
    with pytest.raises(ValueError):
        Databases(tmp_path, "acme/app").names("app_")


def test_drop_never_raises(monkeypatch, tmp_path):
    fake_compose(monkeypatch, tmp_path, COMPOSE)
    dbs = Databases(tmp_path, "acme/app")
    monkeypatch.setattr(dbs, "names", lambda prefix: (_ for _ in ()).throw(OSError("down")))
    assert dbs.drop() == []


def test_a_database_url_overrides_the_compose_file(monkeypatch, tmp_path):
    fake_compose(monkeypatch, tmp_path, COMPOSE)
    s = Databases(tmp_path, "acme/app", "postgres://app:p%40ss@localhost:5547/app_main").server
    assert (s.host, s.port, s.user, s.password, s.dbname) == ("localhost", 5547, "app", "p@ss",
                                                              "app_main")
    assert from_url("postgresql://app@db").port == 5432
    with pytest.raises(ValueError):
        from_url("mysql://app@db/app")
