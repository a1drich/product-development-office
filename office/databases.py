"""Throwaway databases that agents create in the target's Postgres, and dropping them.

Each issue owns a name prefix (`office_<repo hash>_i12_`). Agents name any database they
create with it, and the office drops everything with that prefix after each run on the
issue. Only one agent works on an issue at a time, and the repo hash keeps two targets
sharing one Postgres server apart, so a prefix never belongs to someone else's run. The
office only ever drops names starting with `office_`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from office.shell import run

log = logging.getLogger("office")

PREFIX = "office_"
NAME = re.compile(r"^office_[a-z0-9_]+$")


def repo_prefix(repo: str) -> str:
    return f"{PREFIX}{hashlib.sha1(repo.lower().encode()).hexdigest()[:6]}_"


def prefix_for(repo: str, issue: int) -> str:
    return f"{repo_prefix(repo)}i{issue}_"


@dataclass(frozen=True)
class Server:
    host: str
    port: int
    user: str
    password: str
    dbname: str


def compose_postgres(root: Path) -> Server | None:
    """The target's Postgres, from its docker compose file. Reading the config works
    whichever compose project started the container, and doesn't need it running."""
    if not any((root / n).exists() for n in
               ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")):
        return None
    res = run(["docker", "compose", "config", "--format", "json"], cwd=root, check=False)
    if not res.ok:
        return None
    try:
        services = json.loads(res.stdout).get("services", {})
    except json.JSONDecodeError:
        return None
    for svc in services.values():
        if not str(svc.get("image", "")).startswith("postgres"):
            continue
        env = svc.get("environment") or {}
        port = next((p.get("published") for p in svc.get("ports") or []
                     if p.get("target") == 5432 and p.get("published")), None)
        if not port:
            return None  # not reachable from the host
        user = env.get("POSTGRES_USER") or "postgres"
        return Server("127.0.0.1", int(port), user, env.get("POSTGRES_PASSWORD") or "",
                      env.get("POSTGRES_DB") or user)
    return None


class Databases:
    def __init__(self, root: Path, repo: str):
        self.root = root
        self.prefix = repo_prefix(repo)
        self._server: Server | None = None
        self._looked = False

    @property
    def server(self) -> Server | None:
        if not self._looked:
            self._server = compose_postgres(self.root)
            self._looked = True
        return self._server

    def _connect(self):
        import psycopg

        s = self.server
        return psycopg.connect(host=s.host, port=s.port, user=s.user, password=s.password,
                               dbname=s.dbname, autocommit=True, connect_timeout=5)

    def names(self, prefix: str) -> list[str]:
        if not prefix.startswith(PREFIX):
            raise ValueError(f"refusing to look outside {PREFIX!r}: {prefix!r}")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT datname FROM pg_database WHERE starts_with(datname, %s) ORDER BY 1",
                (prefix,),
            ).fetchall()
        return [r[0] for r in rows if NAME.match(r[0])]

    def drop(self, prefix: str | None = None) -> list[str]:
        """Drops every database starting with `prefix` (which must start with `office_`),
        or by default every database the office made for this repo. Never raises: cleanup
        must not fail the run it follows."""
        prefix = prefix or self.prefix
        if self.server is None:
            return []
        from psycopg import sql

        dropped = []
        try:
            for name in self.names(prefix):
                with self._connect() as conn:
                    conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)")
                                 .format(sql.Identifier(name)))
                dropped.append(name)
        except Exception as e:
            log.warning("could not drop the office's %s* databases: %s", prefix, e)
        return dropped
