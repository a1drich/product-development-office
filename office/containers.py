"""Docker containers, networks and volumes that agents start, and removing them.

Each worktree run gets `COMPOSE_PROJECT_NAME` set to its issue's name (`office_<repo
hash>_i12`, the database prefix without its trailing `_`), so everything compose creates
there carries that project label. Agents name anything they start with plain `docker run`
with the same prefix. After each run the office removes what the issue owns. A container
publishing a port outside the run's lease is kept: it serves something shared, such as the
dev database an agent had to start, and the next `office start` sweeps it up. The office
only ever removes names and projects starting with `office_`.
"""

from __future__ import annotations

import json
import logging
import re

from office.databases import PREFIX, prefix_for
from office.shell import run

log = logging.getLogger("office")

PROJECT = "com.docker.compose.project"


def project_for(repo: str, issue: int) -> str:
    return prefix_for(repo, issue).rstrip("_")


def owned(prefix: str, name: str, project: str) -> bool:
    """`office_abc123_i1_` owns `office_abc123_i1` and `office_abc123_i1_redis`, never
    `office_abc123_i12`."""
    return name.startswith(prefix) or bool(project) and (project + "_").startswith(prefix)


def _docker(*args: str) -> list[str]:
    res = run(["docker", *args], check=False, timeout=60)
    return res.stdout.splitlines() if res.ok else []


def _listed(kind: str, name_field: str, prefix: str) -> list[str]:
    fmt = f"{{{{{name_field}}}}}\t{{{{.Label \"{PROJECT}\"}}}}"
    every = ["-a"] if kind == "container" else []
    rows = (line.split("\t") for line in _docker(kind, "ls", *every, "--format", fmt))
    return [r[0] for r in rows if len(r) == 2 and owned(prefix, *r)]


def published_ports(inspected: dict) -> set[int]:
    bindings = (inspected.get("HostConfig") or {}).get("PortBindings") or {}
    return {int(b["HostPort"]) for bs in bindings.values() for b in bs or []
            if re.fullmatch(r"\d+", str(b.get("HostPort", "")))}


def remove(prefix: str, allowed_ports: set[int] | None = None) -> list[str]:
    """Removes every container, network and volume owned by `prefix` (which must start with
    `office_`). With `allowed_ports`, keeps a container that publishes any other port.
    Returns what it removed. Never raises: cleanup must not fail the run it follows."""
    if not prefix.startswith(PREFIX):
        raise ValueError(f"refusing to look outside {PREFIX!r}: {prefix!r}")
    removed: list[str] = []
    try:
        names = _listed("container", ".Names", prefix)
        if names and allowed_ports is not None:
            inspected = json.loads("\n".join(_docker("container", "inspect", *names)) or "[]")
            kept = {c["Name"].lstrip("/") for c in inspected
                    if published_ports(c) - allowed_ports}
            for name in sorted(kept):
                log.info("kept container %s: it publishes a port outside the run's lease",
                         name)
            names = [n for n in names if n not in kept]
        if names and run(["docker", "rm", "-f", "-v", *names], check=False, timeout=120).ok:
            removed += names
        # Docker refuses to remove a network or volume a kept container still uses.
        for kind, field in (("network", ".Name"), ("volume", ".Name")):
            for name in _listed(kind, field, prefix):
                if run(["docker", kind, "rm", name], check=False, timeout=60).ok:
                    removed.append(name)
    except Exception as e:
        log.warning("could not remove the office's %s* containers: %s", prefix, e)
    return removed
