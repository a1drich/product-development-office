"""Port leases: which ports each running agent may use.

Every engineer, reviewer and tester run gets its own block of ports from an agent-only
range, so agents never collide with each other or with the owner's own dev servers
(the reserved ranges). A block is only handed out when nothing is listening on any of
its ports. Some ports have to match configuration outside the repo, such as a sign-in
provider's allowed origins; those are named fixed sets, and an agent claims one with
`office-lease <name>`, which gives it to one issue at a time.

Leases are files in a leases folder that every office on the machine shares, so offices
on different repos never collide either, and `office plan` and the `office-lease`
command can see them. They last as long as the run: the office releases them, and stops
anything still listening on them, when the run ends, and clears its repo's leftovers at
startup.
"""

from __future__ import annotations

import fcntl
import json
import os
import signal
import socket
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from office.shell import run


def parse_range(text: str) -> range:
    low, _, high = text.partition("-")
    return range(int(low), int(high or low) + 1)


def label(ports: range) -> str:
    return f"{ports.start}-{ports.stop - 1}"


def in_use(port: int) -> bool:
    """True when something is listening on the port, on IPv4 or IPv6."""
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                if s.connect_ex((host, port)) == 0:
                    return True
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            return True
    return False


def listeners(port: int) -> set[int]:
    res = run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], check=False)
    return {int(p) for p in res.stdout.split() if p.isdigit()} - {os.getpid()}


def stop_listeners(ports: list[int]) -> list[int]:
    """Stops whatever is listening on these ports (servers an agent left behind)."""
    stopped = []
    for port in ports:
        for pid in listeners(port):
            try:
                os.kill(pid, signal.SIGTERM)
                stopped.append(pid)
            except (ProcessLookupError, PermissionError):
                pass
    return stopped


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # alive, but owned by someone else
    return True


class Leases:
    """The leases of one repo's office, kept in a folder every office on the machine
    shares, so offices on different repos never hand out the same port.

    Each lease is a JSON file named after the repo: `<owner__repo>.block-<issue>.json` or
    `<owner__repo>.fixed-<name>.json`, holding the issue, its ports and the pid of the
    office that leased them. A lease whose office has exited no longer holds its ports,
    so a crashed office never locks other offices out. Leasing and claiming take a file
    lock, so two offices can't take the same ports at the same moment.
    """

    def __init__(self, folder: Path, owner: str, agent_range: str, block: int,
                 reserved: list[str], fixed: dict[str, list[int]],
                 probe: Callable[[int], bool] = in_use, pid: int | None = None):
        self.folder = folder
        self.owner = owner
        self.range = parse_range(agent_range)
        self.block = block
        self.reserved = [parse_range(r) for r in reserved]
        self.fixed = fixed
        self.probe = probe
        # The office's pid; `office-lease` runs in an agent, on the office's behalf.
        self.pid = pid or os.getpid()
        self.lock = threading.Lock()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.folder.mkdir(parents=True, exist_ok=True)
        with self.lock, (self.folder / ".lock").open("w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def _path(self, kind: str, key: str | int) -> Path:
        return self.folder / f"{self.owner}.{kind}-{key}.json"

    def _write(self, path: Path, issue: int, ports: list[int]) -> None:
        path.write_text(json.dumps({"pid": self.pid, "issue": issue, "ports": ports}))

    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _held(self) -> set[int]:
        """Every port a live lease holds, whichever office leased it."""
        held: set[int] = set()
        for path in self.folder.glob("*.json"):
            rec = self._read(path)
            if rec and alive(rec["pid"]):
                held.update(rec["ports"])
        return held

    def _own(self) -> list[Path]:
        return sorted(self.folder.glob(f"{self.owner}.*.json"))

    def clear(self) -> None:
        """At startup this office runs no agents, so every lease of its repo is left over.
        Other repos' leases belong to their own offices and are left alone."""
        for f in self._own():
            f.unlink(missing_ok=True)

    def _reserved(self, ports: range) -> bool:
        return any(p in r for r in self.reserved for p in ports)

    def lease(self, issue: int) -> range | None:
        """A free block of ports for the issue's run, or None if none is free."""
        with self._locked():
            held = self._held()
            for start in range(self.range.start, self.range.stop - self.block + 1, self.block):
                ports = range(start, start + self.block)
                if held.intersection(ports) or self._reserved(ports):
                    continue
                if any(self.probe(p) for p in ports):
                    continue
                self._write(self._path("block", issue), issue, list(ports))
                return ports
            return None

    def held_by(self, issue: int) -> list[int]:
        """Every port the issue holds: its block and any fixed sets it claimed."""
        ports: list[int] = []
        for f in self._own():
            rec = self._read(f)
            if rec and rec["issue"] == issue:
                ports += rec["ports"]
        return ports

    def release(self, issue: int) -> list[int]:
        """Releases the issue's leases and returns the ports they covered."""
        ports = self.held_by(issue)
        for f in self._own():
            rec = self._read(f)
            if rec and rec["issue"] == issue:
                f.unlink(missing_ok=True)
        return ports

    def claim(self, name: str, issue: int) -> tuple[list[int] | None, str]:
        """Claims a fixed set for the issue: (ports, "") or (None, why not)."""
        if name not in self.fixed:
            known = ", ".join(self.fixed) or "none are configured"
            return None, f"no fixed port set named {name!r} ({known})"
        wanted = self.fixed[name]
        path = self._path("fixed", name)
        with self._locked():
            rec = self._read(path) if path.exists() else None
            if rec and alive(rec["pid"]):
                if rec["issue"] == issue:
                    return wanted, ""
                return None, f"busy: held by #{rec['issue']} until its run ends"
            taken = sorted(self._held().intersection(wanted))
            if taken:
                return None, (f"busy: another agent's lease (possibly another repo's office) "
                              f"holds {', '.join(map(str, taken))}")
            busy = [p for p in wanted if self.probe(p)]
            if busy:
                return None, (f"busy: something outside the office is listening on "
                              f"{', '.join(map(str, busy))}")
            self._write(path, issue, wanted)
            return wanted, ""

    def table(self) -> list[tuple[str, int, str]]:
        """(lease, issue, ports) for every current lease of this repo, for `office plan`."""
        rows = []
        for f in self._own():
            rec = self._read(f)
            if not rec:
                continue
            kind, _, key = f.name.removeprefix(f"{self.owner}.").removesuffix(".json") \
                .partition("-")
            if kind == "block":
                rows.append(("ports", rec["issue"], label(range(rec["ports"][0],
                                                                rec["ports"][-1] + 1))))
            else:
                rows.append((key, rec["issue"], ", ".join(map(str, rec["ports"]))))
        return rows


def cli(argv: list[str]) -> int:
    """`office-lease <name>`, run by an agent: claims a fixed port set for its issue."""
    from office.config import Config
    from office.workspace import folder_name

    issue = os.environ.get("OFFICE_ISSUE")
    folder = os.environ.get("OFFICE_LEASES")
    repo = os.environ.get("OFFICE_REPO")
    office_pid = os.environ.get("OFFICE_PID", "")
    if len(argv) != 1 or not issue or not folder or not repo or not office_pid.isdigit():
        print("usage: office-lease <name> (only inside an office agent run)", file=sys.stderr)
        return 2
    cfg = Config.load().for_repo(repo)
    # The lease is the office's: it lasts until the office releases it, not until this
    # command exits.
    leases = Leases(Path(folder), folder_name(repo), cfg.agent_ports, cfg.ports_per_agent,
                    cfg.reserved_ports, cfg.fixed_ports, pid=int(office_pid))
    ports, why = leases.claim(argv[0], int(issue))
    if ports is None:
        print(why, file=sys.stderr)
        return 1
    print(" ".join(map(str, ports)))
    return 0
