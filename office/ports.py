"""Port leases: which ports each running agent may use.

Every engineer, reviewer and tester run gets its own block of ports from an agent-only
range, so agents never collide with each other or with the owner's own dev servers
(the reserved ranges). A block is only handed out when nothing is listening on any of
its ports. Some ports have to match configuration outside the repo, such as a sign-in
provider's allowed origins; those are named fixed sets, and an agent claims one with
`office-lease <name>`, which gives it to one issue at a time.

Leases are files in the repo's leases folder, so `office plan` and the `office-lease`
command can see them. They last as long as the run: the office releases them, and stops
anything still listening on them, when the run ends, and clears the folder at startup.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
from collections.abc import Callable
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


class Leases:
    def __init__(self, folder: Path, agent_range: str, block: int, reserved: list[str],
                 fixed: dict[str, list[int]], probe: Callable[[int], bool] = in_use):
        self.folder = folder
        self.range = parse_range(agent_range)
        self.block = block
        self.reserved = [parse_range(r) for r in reserved]
        self.fixed = fixed
        self.probe = probe
        self.lock = threading.Lock()

    def clear(self) -> None:
        """At startup no agents run, so every lease is left over."""
        if self.folder.exists():
            for f in self.folder.iterdir():
                f.unlink(missing_ok=True)

    def _held_blocks(self) -> set[int]:
        if not self.folder.exists():
            return set()
        return {parse_range(f.read_text()).start for f in self.folder.glob("block-*")}

    def _reserved(self, ports: range) -> bool:
        return any(p in r for r in self.reserved for p in ports)

    def lease(self, issue: int) -> range | None:
        """A free block of ports for the issue's run, or None if none is free."""
        with self.lock:
            held = self._held_blocks()
            for start in range(self.range.start, self.range.stop - self.block + 1, self.block):
                ports = range(start, start + self.block)
                if start in held or self._reserved(ports):
                    continue
                if any(self.probe(p) for p in ports):
                    continue
                self.folder.mkdir(parents=True, exist_ok=True)
                (self.folder / f"block-{issue}").write_text(label(ports))
                return ports
            return None

    def held_by(self, issue: int) -> list[int]:
        """Every port the issue holds: its block and any fixed sets it claimed."""
        ports: list[int] = []
        block = self.folder / f"block-{issue}"
        if block.exists():
            ports += list(parse_range(block.read_text()))
        for name, fixed in self.fixed.items():
            f = self.folder / f"fixed-{name}"
            if f.exists() and f.read_text().strip() == str(issue):
                ports += fixed
        return ports

    def release(self, issue: int) -> list[int]:
        """Releases the issue's leases and returns the ports they covered."""
        ports = self.held_by(issue)
        (self.folder / f"block-{issue}").unlink(missing_ok=True)
        for name in self.fixed:
            f = self.folder / f"fixed-{name}"
            if f.exists() and f.read_text().strip() == str(issue):
                f.unlink(missing_ok=True)
        return ports

    def claim(self, name: str, issue: int) -> tuple[list[int] | None, str]:
        """Claims a fixed set for the issue: (ports, "") or (None, why not)."""
        if name not in self.fixed:
            known = ", ".join(self.fixed) or "none are configured"
            return None, f"no fixed port set named {name!r} ({known})"
        f = self.folder / f"fixed-{name}"
        self.folder.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(f, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = f.read_text().strip()
            if holder == str(issue):
                return self.fixed[name], ""
            return None, f"busy: held by #{holder} until its run ends"
        with os.fdopen(fd, "w") as out:
            out.write(str(issue))
        busy = [p for p in self.fixed[name] if self.probe(p)]
        if busy:
            f.unlink(missing_ok=True)
            return None, (f"busy: something outside the office is listening on "
                          f"{', '.join(map(str, busy))}")
        return self.fixed[name], ""

    def table(self) -> list[tuple[str, int, str]]:
        """(lease, issue, ports) for every current lease, for `office plan`."""
        rows = []
        if self.folder.exists():
            for f in sorted(self.folder.iterdir()):
                kind, _, rest = f.name.partition("-")
                if kind == "block":
                    rows.append(("ports", int(rest), f.read_text().strip()))
                elif kind == "fixed" and rest in self.fixed:
                    rows.append((rest, int(f.read_text().strip()),
                                 ", ".join(map(str, self.fixed[rest]))))
        return rows


def cli(argv: list[str]) -> int:
    """`office-lease <name>`, run by an agent: claims a fixed port set for its issue."""
    from office.config import Config

    issue = os.environ.get("OFFICE_ISSUE")
    folder = os.environ.get("OFFICE_LEASES")
    if len(argv) != 1 or not issue or not folder:
        print("usage: office-lease <name> (only inside an office agent run)", file=sys.stderr)
        return 2
    cfg = Config.load()
    leases = Leases(Path(folder), cfg.agent_ports, cfg.ports_per_agent, cfg.reserved_ports,
                    cfg.fixed_ports)
    ports, why = leases.claim(argv[0], int(issue))
    if ports is None:
        print(why, file=sys.stderr)
        return 1
    print(" ".join(map(str, ports)))
    return 0
