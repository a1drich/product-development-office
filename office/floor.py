"""The office floor: one long-running loop over every repo the office works on.

All the repos belong to the same owner and share the machine's one Claude and one
ChatGPT subscription, so they share one set of limits. Each pass collects what every
repo could start, takes the most urgent first across all of them (ties go to each repo
in turn), and starts tasks within each role's limit, counting agents running in any repo.
A role that hits its usage limit pauses for every repo. Stopping drains every repo
together.
"""

from __future__ import annotations

import logging
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from office import ghshim, planner, ports, shell
from office.config import Config
from office.orchestrator import CURRENT_REPO, Office, RepoPrefix, Shared
from office.planner import Task

log = logging.getLogger("office")


class Floor:
    def __init__(self, cfg: Config, offices: list[Office], shared: Shared):
        self.cfg = cfg  # machine-wide settings: limits, poll intervals
        self.offices = offices
        self.shared = shared
        self.turn = 0  # which repo goes first among equally urgent tasks

    @property
    def dry_run(self) -> bool:
        return any(o.dry_run for o in self.offices)

    def running(self) -> int:
        return sum(len(o.running) for o in self.offices)

    def busy(self) -> dict[str, int]:
        """Agents running per role, across every repo."""
        busy: dict[str, int] = {}
        for o in self.offices:
            for role, n in planner.busy_roles(o.running).items():
                busy[role] = busy.get(role, 0) + n
        return busy

    def cycle(self) -> list[Task]:
        """One planning pass over every repo. Starts tasks and returns them."""
        now = datetime.now(UTC)
        n = len(self.offices)
        order = [self.offices[(self.turn + i) % n] for i in range(n)]
        self.turn += 1
        rank = {o.gh.repo: i for i, o in enumerate(order)}
        issues, found = {}, []
        for o in order:
            CURRENT_REPO.set(o.gh.repo)
            issues[o.gh.repo] = o.gh.open_issues()
            found += o.candidates(issues[o.gh.repo], now)
        CURRENT_REPO.set("")
        found.sort(key=lambda t: (t.priority, rank[t.repo], t.issue))
        paused = {role for role, until in self.shared.paused_until.items() if until > now}
        tasks = planner.select(found, self.busy(), self.cfg.limits, paused)
        by_repo = {o.gh.repo: o for o in self.offices}
        for o in order:
            CURRENT_REPO.set(o.gh.repo)
            mine = [t for t in tasks if t.repo == o.gh.repo]
            if o.dry_run:
                o.log_overview(issues[o.gh.repo], now)
                for t in mine:
                    log.info("would run %s on #%s (%s)", t.kind, t.issue,
                             t.role or ("office" if t.kind in planner.OFFICE_RUN
                                        else "housekeeping"))
                continue
            for t in mine:
                by_repo[t.repo].start(t)
            # Work held back by a limit shared with the other repos isn't waiting on a human.
            queued = any(t.repo == o.gh.repo for t in found)
            if not queued and not o.running:
                o.post_summary(issues[o.gh.repo])
        CURRENT_REPO.set("")
        return tasks

    def reap(self) -> None:
        for o in self.offices:
            o.reap()

    def run(self, exit_when_idle: bool = False) -> None:
        prefix = RepoPrefix() if len(self.offices) > 1 else None
        if prefix:
            log.addFilter(prefix)
        try:
            if self.dry_run:
                self.each(lambda o: o.bootstrap())
                with ThreadPoolExecutor(max_workers=1) as pool:
                    self.shared.pool = pool
                    self.loop(exit_when_idle)
                return
            self.serve(exit_when_idle)
        finally:
            if prefix:
                log.removeFilter(prefix)

    def serve(self, exit_when_idle: bool) -> None:
        acquired = []
        try:
            for o in self.offices:  # one office per repo: refuse if any is already running
                o.ws.acquire_pidfile()
                acquired.append(o)
            ghshim.install()
            self.each(lambda o: o.leases.clear())
            self.assign_docs_ports()
            previous = {sig: signal.signal(sig, self.on_signal)
                        for sig in (signal.SIGINT, signal.SIGTERM)}
            try:
                workers = sum(self.cfg.limits.values()) + len(self.offices)
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    self.shared.pool = pool
                    try:
                        self.each(lambda o: (o.recover_claims(), o.sweep_databases(),
                                             o.sweep_containers(), o.bootstrap()))
                        self.loop(exit_when_idle)
                    finally:
                        pool.shutdown(wait=True, cancel_futures=True)
                        self.each(lambda o: o.docs.stop())
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
        finally:
            for o in acquired:
                o.ws.release_pidfile()

    def each(self, fn) -> None:
        for o in self.offices:
            CURRENT_REPO.set(o.gh.repo)
            fn(o)
        CURRENT_REPO.set("")

    def assign_docs_ports(self) -> None:
        """Each repo's docs site gets its own port: its `docs_port`, or the next one up
        that's free and not already another repo's. Repos without a site yet get one too,
        since a merge can add the site while the office runs."""
        taken: set[int] = set()
        for o in self.offices:
            port = o.cfg.docs_port
            while port in taken or ports.in_use(port):
                port += 1
            taken.add(port)
            o.docs.port = port

    def on_signal(self, signum, frame) -> None:
        """First Ctrl-C (or `office stop`) drains; a second one (or `office stop --now`, which
        sends SIGTERM) stops now."""
        if signum == signal.SIGINT and not self.shared.draining.is_set():
            self.shared.draining.set()
            log.info("draining: starting nothing new; %s agent(s) finishing their step. "
                     "Ctrl-C again, or `office stop --now`, to stop them now.", self.running())
        else:
            self.hard_stop()

    def hard_stop(self) -> None:
        self.shared.stopping.set()
        self.shared.draining.set()
        ended = shell.stop_all()
        log.info("stopping now: ended %s running command(s); interrupted steps rerun at the "
                 "next start", ended)

    def loop(self, exit_when_idle: bool) -> None:
        while True:
            self.reap()
            if self.shared.draining.is_set():
                if not self.running():
                    log.info("all agents finished; stopped")
                    return
                if self.shared.stopping.is_set():
                    shell.stop_all()
                time.sleep(1)
                continue
            if not self.dry_run:
                self.each(lambda o: o.docs.ensure())
            started = self.cycle()
            if self.dry_run:
                return
            idle = not started and not self.running()
            if idle and exit_when_idle:
                log.info("nothing left to act on; exiting")
                return
            # Wakes early when a drain or stop is requested.
            self.shared.draining.wait(self.cfg.idle_poll_seconds if idle
                                      else self.cfg.poll_seconds)
