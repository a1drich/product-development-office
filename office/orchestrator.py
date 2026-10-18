"""The long-running loop: poll GitHub, plan tasks from labels, run agents, apply verdicts."""

from __future__ import annotations

import logging
import re
import signal
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from office import labels as L
from office import planner, readiness, shell
from office.agents import AgentResult, Verdict, render, run_agent
from office.config import ROOT, Config
from office.docs_server import DocsServer
from office.gh import GitHub, Issue, branch_name
from office.planner import CLAIM_MARK, FAILED_MARK, Task
from office.readiness import verify_command
from office.workspace import Workspace

log = logging.getLogger("office")

MAX_FAILURES = 3
CI_WAIT_SECONDS = 30 * 60
STATUS_TITLE = "Office status"
SCREENSHOT_DIR = "docs/manual/screenshots/"


def mark(name: str) -> str:
    return f"<!-- office:{name} -->"


def normalize_title(title: str) -> str:
    """Compare titles ignoring case, punctuation, articles and a `Practice:` prefix."""
    title = re.sub(r"^\s*practice:\s*", "", title, flags=re.I)
    words = re.findall(r"[a-z0-9]+", title.lower())
    return " ".join(w for w in words if w not in {"a", "an", "the"})


def format_open_issues(titles: dict[int, str], exclude: int) -> str:
    shown = [f"- #{n} {t}" for n, t in sorted(titles.items()) if n != exclude and t != STATUS_TITLE]
    return "\n".join(shown) or "(none)"


def format_comments(issue: Issue, limit: int = 30) -> str:
    shown = [c for c in issue.comments if CLAIM_MARK not in c.body][-limit:]
    if not shown:
        return "(none)"
    return "\n\n".join(f"**@{c.author}** ({c.created_at:%Y-%m-%d %H:%M}):\n{c.body}" for c in shown)


IMPECCABLE_BODY = f"""\
The Designer plans UI work with the [impeccable](https://github.com/pbakaus/impeccable) design \
skill, engineers use it for UI changes, and the tester runs its `detect` command. It isn't \
committed to this repo yet, and agents work from fresh clones, so it has to be.

## Acceptance criteria
- [ ] `npx skills add pbakaus/impeccable` has been run at the repo root.
- [ ] The installed skill (`{readiness.IMPECCABLE_DIRS[0]}` and/or \
`{readiness.IMPECCABLE_DIRS[1]}`) is committed. Nothing else changes.
- [ ] The verify command passes.

Design work waits until this issue closes.
{mark("setup")}"""


def blocker_body(blocker: dict, blocks: list[int]) -> str:
    options = "\n".join(f"{i}. {opt}" for i, opt in enumerate(blocker.get("options") or [], 1))
    return (
        f"## Decision needed\n{blocker.get('decision', '').strip()}\n\n"
        f"## Context\n{blocker.get('context', '').strip()}\n\n"
        f"## Options\n{options or '(none given)'}\n\n"
        f"## Recommendation\n{blocker.get('recommendation', '').strip()}\n\n"
        f"## Blocks\n{', '.join(f'#{n}' for n in blocks)}\n\n"
        "---\nTo answer: comment with your decision, then remove the `blocked:human` label.\n"
        f"{mark('blocker')}"
    )


class Office:
    def __init__(self, cfg: Config, gh: GitHub, ws: Workspace, dry_run: bool = False):
        self.cfg = cfg
        self.gh = gh
        self.ws = ws
        self.dry_run = dry_run
        self.running: dict[int, str] = {}
        self.futures: dict[Future, Task] = {}
        self.paused_until: dict[str, datetime] = {}
        self.last_summary = ""
        self.status_issue: int | None = None
        # draining: start nothing new, let running agents finish, then exit.
        # stopping: stop now; running agents are ended and their runs don't count.
        self.draining = threading.Event()
        self.stopping = threading.Event()
        self.docs = DocsServer(ws.clone, cfg.docs_port, ws.docs_log)
        self.last_practices: datetime | None = None
        self.verify = verify_command(ws.clone) or "the repo's verify command (see AGENTS.md)"

    # --- loop -------------------------------------------------------------------

    def paused(self, now: datetime) -> set[str]:
        return {role for role, until in self.paused_until.items() if until > now}

    def cycle(self) -> list[Task]:
        """One planning pass. Starts tasks and returns them."""
        now = datetime.now(UTC)
        issues = self.gh.open_issues()
        # Design needs impeccable, so it waits while the setup issue is open.
        setup_open = any(i.title == readiness.IMPECCABLE_TITLE for i in issues)
        tasks = planner.plan(
            issues,
            self.running,
            self.cfg.limits,
            self.paused(now),
            now,
            timedelta(minutes=self.cfg.claim_ttl_minutes),
            held=frozenset({"design"}) if setup_open else frozenset(),
        )
        practices = self.practices_task(issues, tasks, now)
        if practices:
            tasks.append(practices)
        if self.dry_run:
            self.log_overview(issues, now)
            for t in tasks:
                log.info("would run %s on #%s (%s)", t.kind, t.issue, t.role or "housekeeping")
            return tasks
        for task in tasks:
            self.start(task)
        if not tasks and not self.running:
            self.post_summary(issues)
        return tasks

    # --- practices --------------------------------------------------------------

    def practices_task(self, issues: list[Issue], tasks: list[Task], now: datetime) -> Task | None:
        """A practices review, when one is due and the PM has a free slot."""
        open_practices = [i for i in issues if L.PRACTICE in i.labels]
        if len(open_practices) >= self.cfg.max_open_practices:
            return None
        pm_busy = sum(1 for r in self.running.values() if r == "pm")
        pm_busy += sum(1 for t in tasks if t.role == "pm")
        if "pm" in self.paused(now) or pm_busy >= self.cfg.limits.get("pm", 1):
            return None
        number = self.ensure_status_issue()
        if number in self.running:
            return None
        if self.last_practices is None:
            # A dry run on a repo with no status issue yet has number 0: never reviewed.
            comments = self.gh.issue(number).comments if number else []
            marks = [c.created_at for c in comments if mark("practices") in c.body]
            self.last_practices = max(marks) if marks else datetime.min.replace(tzinfo=UTC)
        if now - self.last_practices < timedelta(hours=self.cfg.practices_interval_hours):
            return None
        return Task("practices", number)

    def do_practices(self, issue: Issue, task: Task) -> None:
        findings = [f for f in readiness.check_files(self.ws.clone) if f.level != readiness.PASS]
        open_practices = [i for i in self.gh.open_issues() if L.PRACTICE in i.labels]
        values = self.values(
            issue,
            findings="\n".join(f"- {f.level}: {f.summary}. {f.fix.splitlines()[0]}"
                               for f in findings if f.fix) or "(all automated checks pass)",
            open_practices="\n".join(f"- #{i.number} {i.title}" for i in open_practices)
            or "(none)",
            max_new=str(max(1, self.cfg.max_open_practices - len(open_practices))),
        )
        self.last_practices = datetime.now(UTC)
        result = self.in_clone("pm", render("pm_practices", values))
        verdict = self.accept(issue, task, result, {"done"})
        filed = len(verdict.new_issues) if verdict else 0
        self.gh.comment(issue.number, f"Practices review: {filed} suggestion(s) filed.\n"
                                      f"{mark('practices')}")

    def ensure_status_issue(self) -> int:
        if self.status_issue is None:
            self.status_issue = self.gh.find_issue_by_title(STATUS_TITLE, L.STATUS_ISSUE)
        if self.status_issue is None and not self.dry_run:
            self.status_issue = self.gh.create_issue(
                STATUS_TITLE,
                f"The office is running. This issue lists what is waiting on a human.\n"
                f"{mark('status')}",
                [L.STATUS_ISSUE],
            )
        return self.status_issue or 0

    def log_overview(self, issues: list[Issue], now: datetime) -> None:
        ttl = timedelta(minutes=self.cfg.claim_ttl_minutes)
        counts: dict[str, int] = {}
        for i in issues:
            t = planner.task_for(i, now, ttl, {x.number for x in issues})
            key = t.kind if t else "waiting on a human" if i.blocked else "in progress / other"
            counts[key] = counts.get(key, 0) + 1
        summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1]))
        log.info("%s open issues: %s", len(issues), summary or "none")

    def run(self, exit_when_idle: bool = False) -> None:
        if self.dry_run:
            self.bootstrap()
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.pool = pool
                self.loop(exit_when_idle)
            return
        self.ws.acquire_pidfile()
        previous = {sig: signal.signal(sig, self.on_signal)
                    for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            with ThreadPoolExecutor(max_workers=sum(self.cfg.limits.values()) + 1) as pool:
                self.pool = pool
                try:
                    self.recover_claims()
                    self.bootstrap()
                    self.loop(exit_when_idle)
                finally:
                    pool.shutdown(wait=True, cancel_futures=True)
                    self.docs.stop()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            self.ws.release_pidfile()

    def on_signal(self, signum, frame) -> None:
        """First Ctrl-C (or `office stop`) drains; a second one (or `office stop --now`, which
        sends SIGTERM) stops now."""
        if signum == signal.SIGINT and not self.draining.is_set():
            self.draining.set()
            log.info("draining: starting nothing new; %s agent(s) finishing their step. "
                     "Ctrl-C again, or `office stop --now`, to stop them now.", len(self.running))
        else:
            self.hard_stop()

    def hard_stop(self) -> None:
        self.stopping.set()
        self.draining.set()
        ended = shell.stop_all()
        log.info("stopping now: ended %s running command(s); interrupted steps rerun at the "
                 "next start", ended)

    def recover_claims(self) -> None:
        """A fresh office has no agents running, so every in-progress claim is left over
        from a previous run that stopped. Release them now instead of waiting for them to
        expire."""
        for issue in self.gh.open_issues():
            if issue.status == L.IN_PROGRESS:
                self.gh.set_status(issue, L.READY)
                self.gh.comment(issue.number, "The office restarted; releasing the previous "
                                              f"claim.\n{mark('release')}")
                log.info("#%s: released a claim left over from the last run", issue.number)

    def bootstrap(self) -> None:
        """Every target needs impeccable before design work. If the clone doesn't have it,
        file a ready, p0 issue so an engineer adds it in a PR that is reviewed and tested
        like any other change. The office never commits to the target itself."""
        if readiness.impeccable_installed(self.ws.clone):
            return
        if self.gh.find_issue_by_title(readiness.IMPECCABLE_TITLE):
            return
        if self.dry_run:
            log.info("would file %r (impeccable isn't committed)", readiness.IMPECCABLE_TITLE)
            return
        n = self.gh.create_issue(readiness.IMPECCABLE_TITLE, IMPECCABLE_BODY,
                                 [L.READY, "priority:p0"])
        log.info("filed #%s: %s", n, readiness.IMPECCABLE_TITLE)

    def loop(self, exit_when_idle: bool) -> None:
        while True:
            self.reap()
            if self.draining.is_set():
                if not self.running:
                    log.info("all agents finished; stopped")
                    return
                if self.stopping.is_set():
                    shell.stop_all()
                time.sleep(1)
                continue
            if not self.dry_run:
                self.docs.ensure()
            started = self.cycle()
            if self.dry_run:
                return
            idle = not started and not self.running
            if idle and exit_when_idle:
                log.info("nothing left to act on; exiting")
                return
            # Wakes early when a drain or stop is requested.
            self.draining.wait(self.cfg.idle_poll_seconds if idle else self.cfg.poll_seconds)

    def start(self, task: Task) -> None:
        if task.kind in planner.HOUSEKEEPING:
            self.safely(task, self.housekeeping)
            return
        self.running[task.issue] = task.role
        log.info("starting %s on #%s (%s)", task.kind, task.issue, task.role)
        self.futures[self.pool.submit(self.safely, task, self.execute)] = task

    def reap(self) -> None:
        for fut in [f for f in self.futures if f.done()]:
            task = self.futures.pop(fut)
            self.running.pop(task.issue, None)

    def safely(self, task: Task, fn) -> None:
        try:
            fn(task)
        except Exception as e:  # one bad task must not stop the office
            log.exception("%s on #%s crashed", task.kind, task.issue)
            try:
                self.record_failure(self.gh.issue(task.issue), task, f"office error: {e}")
            except Exception:
                log.exception("could not record failure on #%s", task.issue)

    # --- housekeeping -----------------------------------------------------------

    def housekeeping(self, task: Task) -> None:
        issue = self.gh.issue(task.issue)
        if task.kind == "release":
            log.info("releasing stale claim on #%s", issue.number)
            self.gh.set_status(issue, L.READY)
            note = f"Released a stale claim; back to ready.\n{mark('release')}"
            self.gh.comment(issue.number, note)
        elif task.kind == "unwait":
            self.gh.edit_labels(issue.number, remove=[L.WAITING])
            deps = ", ".join(f"#{n}" for n in planner.dependencies(issue)) or "its dependencies"
            self.gh.comment(issue.number, f"{deps} closed; back in the queue.\n{mark('unwait')}")
            log.info("#%s no longer waiting", issue.number)
        elif task.kind == "close_done":
            self.gh.close_issue(issue.number, f"Done.\n{mark('closed')}")

    def post_summary(self, issues: list[Issue]) -> None:
        waiting = sorted((i for i in issues if i.blocked),
                         key=lambda i: (not i.is_blocker, L.PRACTICE in i.labels,
                                        planner.priority(i), i.number))
        lines = [f"- #{i.number} {i.title}" for i in waiting]
        summary = "\n".join(lines) or "- (none)"
        if summary == self.last_summary:
            return
        self.last_summary = summary
        docs = (f"\n\nThe manual and feature catalog (live while the office runs): "
                f"{self.docs.url}" if self.docs.available else "")
        body = (
            "The office has nothing it can act on. These issues are waiting on a human "
            "(office decisions first, then practice suggestions, then by priority):\n\n"
            f"{summary}{docs}\n\n{mark('status')}"
        )
        log.info("idle. open blockers:\n%s", summary)
        self.gh.edit_body(self.ensure_status_issue(), body)

    # --- agent tasks ------------------------------------------------------------

    def execute(self, task: Task) -> None:
        issue = self.gh.issue(task.issue)
        handler = getattr(self, f"do_{task.kind}")
        handler(issue, task)

    def values(self, issue: Issue, **extra: str) -> dict[str, str]:
        return {
            "repo": self.gh.repo,
            "number": str(issue.number),
            "title": issue.title,
            "body": issue.body or "(empty)",
            "comments": format_comments(issue),
            "open_issues": format_open_issues(self.gh.open_issue_titles(), issue.number),
            "verify": self.verify,
            "branch": branch_name(issue.number),
            "base": self.ws.default_branch(),
            "shoot": f"uv run --project {ROOT} office shoot",
            "docs_build": "uvx --with mkdocs-material mkdocs build --strict",
            **extra,
        }

    def in_clone(self, role: str, prompt: str) -> AgentResult:
        self.ws.update_default_branch()
        return run_agent(role, prompt, self.ws.clone, self.cfg)

    def do_triage(self, issue: Issue, task: Task) -> None:
        if issue.status is None:
            self.gh.set_status(issue, L.TRIAGE)
        result = self.in_clone("pm", render("pm", self.values(issue)))
        verdict = self.accept(issue, task, result,
                              {"ready", "design", "blocked", "close", "waiting"})
        if not verdict:
            return
        if verdict.outcome == "ready":
            self.advance(issue, L.READY, verdict)
        elif verdict.outcome == "design":
            self.advance(issue, L.DESIGN, verdict)
        elif verdict.outcome == "close":
            note = f"Closed by the PM: {verdict.summary}\n{mark('closed')}"
            self.gh.close_issue(issue.number, note)
            log.info("#%s closed by the PM: %s", issue.number, verdict.summary[:200])

    def do_design(self, issue: Issue, task: Task) -> None:
        result = self.in_clone("designer", render("designer", self.values(issue)))
        verdict = self.accept(issue, task, result, {"ready", "blocked", "waiting"})
        if verdict and verdict.outcome == "ready":
            self.advance(issue, L.READY, verdict)

    def do_implement(self, issue: Issue, task: Task) -> None:
        self.gh.assign_self(issue.number)
        self.gh.set_status(issue, L.IN_PROGRESS)
        self.gh.comment(issue.number, f"An engineer picked this up.\n{CLAIM_MARK}")
        pr = self.gh.pr_for_issue(issue.number)
        pr_context = (
            f"PR #{pr['number']} already exists for this branch. Read its review and test "
            f"feedback with `gh pr view {pr['number']} --repo {self.gh.repo} --comments` and "
            "address every blocking finding."
            if pr else "No PR exists yet."
        )
        path = self.ws.worktree(issue.number)
        prompt = render("engineer", self.values(issue, pr_context=pr_context))
        result = run_agent("engineer", prompt, path, self.cfg, exclusive=True)
        verdict = self.accept(issue, task, result, {"opened", "blocked", "failed", "waiting"},
                              fallback_status=L.READY)
        if not verdict:
            return
        if verdict.outcome == "failed":
            self.record_failure(issue, task, verdict.summary, status=L.READY)
            return
        if verdict.outcome == "opened":
            pr = self.gh.pr_for_issue(issue.number)
            if not pr:
                self.record_failure(issue, task, "engineer reported a PR but none is open for "
                                    f"`{branch_name(issue.number)}`", status=L.READY)
                return
            self.advance(issue, L.IN_REVIEW, verdict, f"PR #{pr['number']}")

    def pr_or_requeue(self, issue: Issue, task: Task) -> dict | None:
        """The issue's open PR, if it can go to review or test. A PR that conflicts with
        the base branch goes straight back to an engineer, without spending a Codex run."""
        pr = self.gh.pr_for_issue(issue.number)
        if not pr:
            self.record_failure(issue, task, f"no open PR for `{branch_name(issue.number)}`",
                                status=L.READY)
            return None
        if self.gh.pr_conflicts(pr["number"]):
            self.gh.set_status(issue, L.READY)
            self.gh.comment(issue.number,
                            f"PR #{pr['number']} conflicts with `{self.ws.default_branch()}`. "
                            "Merge the latest base branch into it and resolve the conflicts.\n"
                            f"{mark('conflict')}")
            log.info("#%s: PR #%s conflicts with base; back to an engineer", issue.number,
                     pr["number"])
            return None
        return pr

    def do_review(self, issue: Issue, task: Task) -> None:
        pr = self.pr_or_requeue(issue, task)
        if not pr:
            return
        path = self.ws.worktree(issue.number)
        prompt = render("reviewer", self.values(issue, pr=str(pr["number"])))
        result = run_agent("reviewer", prompt, path, self.cfg, exclusive=True)
        verdict = self.accept(issue, task, result, {"approve", "changes", "blocked"})
        if not verdict:
            return
        if verdict.outcome == "approve":
            self.advance(issue, L.TESTING, verdict, f"Review approved PR #{pr['number']}")
        elif verdict.outcome == "changes":
            self.advance(issue, L.READY, verdict, f"Review requested changes on PR #{pr['number']}")

    def do_test(self, issue: Issue, task: Task) -> None:
        pr = self.pr_or_requeue(issue, task)
        if not pr:
            return
        path = self.ws.worktree(issue.number)
        prompt = render("tester", self.values(issue, pr=str(pr["number"])))
        result = run_agent("tester", prompt, path, self.cfg, exclusive=True)
        verdict = self.accept(issue, task, result, {"pass", "fail", "blocked"})
        if not verdict:
            return
        if verdict.outcome == "fail":
            self.advance(issue, L.READY, verdict, f"Testing failed PR #{pr['number']}")
            return
        if verdict.outcome == "pass":
            self.merge(issue, task, pr["number"], verdict)

    def merge(self, issue: Issue, task: Task, pr: int, verdict: Verdict) -> None:
        deadline = time.monotonic() + CI_WAIT_SECONDS
        while True:
            passing, detail = self.gh.pr_checks_passing(pr)
            if passing:
                break
            if self.stopping.is_set():
                return  # still `status:testing`; the next start tests it again
            if "fail" in detail.lower() or time.monotonic() > deadline:
                self.advance(issue, L.READY, verdict,
                             f"Tests passed locally but CI did not pass on PR #{pr}:\n\n```\n"
                             f"{detail[-1500:]}\n```")
                return
            self.stopping.wait(60)
        screens = self.screens_markdown(pr)
        if screens:
            self.gh.pr_comment(pr, f"## Screens in this change\n\n{screens}\n{mark('screens')}")
        self.gh.merge_pr(pr)
        self.advance(issue, L.DONE, verdict, f"Tested and merged PR #{pr}")
        self.ws.remove_worktree(issue.number)
        # Refresh the main clone, so the live docs site shows the merged change.
        self.ws.update_default_branch()
        if screens:
            self.gh.comment(
                self.ensure_status_issue(),
                f"### Screens changed by PR #{pr} (#{issue.number} {issue.title})\n\n"
                f"Please review them, and the manual at {self.docs.url}.\n\n{screens}\n"
                f"{mark('screens')}",
            )
        fresh = self.gh.issue(issue.number)
        if fresh.state == "OPEN":
            self.gh.close_issue(issue.number)

    def screens_markdown(self, pr: int) -> str:
        """Image grid of the manual screenshots a PR adds or changes."""
        sha, files = self.gh.pr_files(pr)
        shots = sorted(f for f in files if f.startswith(SCREENSHOT_DIR) and f.endswith(".png"))
        if not shots:
            return ""
        base = f"https://github.com/{self.gh.repo}/blob/{sha}"
        return "\n".join(f"**{f.rsplit('/', 1)[-1]}**\n\n![{f}]({base}/{f}?raw=true)\n"
                         for f in shots)

    def do_resolve_blocker(self, issue: Issue, task: Task) -> None:
        result = self.in_clone("pm", render("pm_blocker", self.values(issue)))
        verdict = self.accept(issue, task, result, {"resolved", "blocked"}, file_blocker=False)
        if not verdict:
            return
        if verdict.outcome == "blocked":
            note = (verdict.blocker or {}).get("decision") or verdict.summary
            self.gh.edit_labels(issue.number, add=[L.BLOCKED])
            self.gh.comment(issue.number, f"Still needs an answer: {note}\n{mark('still-blocked')}")
            return
        for n in planner.blocks_section(issue.body):
            self.gh.edit_labels(n, remove=[L.BLOCKED])
            self.gh.comment(n, f"Unblocked by #{issue.number}.\n{mark('unblocked')}")
        self.gh.close_issue(issue.number, f"Applied: {verdict.summary}\n{mark('resolved')}")

    # --- verdict handling -------------------------------------------------------

    def accept(
        self,
        issue: Issue,
        task: Task,
        result: AgentResult,
        allowed: set[str],
        fallback_status: str | None = None,
        file_blocker: bool = True,
    ) -> Verdict | None:
        """Validates a result, files follow-ups and blockers. Returns the verdict to act on."""
        if result.rate_limited:
            until = datetime.now(UTC) + timedelta(minutes=self.cfg.rate_limit_pause_minutes)
            self.paused_until[result.role] = until
            log.warning("%s hit its usage limit; pausing the role until %s", result.role,
                        f"{until:%H:%M} UTC")
            if fallback_status:
                self.gh.set_status(issue, fallback_status)
            return None
        verdict = result.verdict
        if verdict is None or verdict.outcome not in allowed:
            got = verdict.outcome if verdict else "no verdict"
            self.record_failure(issue, task, result.error or f"unexpected outcome {got!r}",
                                status=fallback_status)
            return None
        for new in verdict.new_issues:
            self.file_follow_up(issue, new["title"], new["body"])
        if verdict.outcome == "waiting":
            self.wait(issue, task, verdict)
            return None
        if verdict.outcome == "blocked":
            if file_blocker:
                self.file_blocker(issue, verdict)
            return verdict if not file_blocker else None
        return verdict

    def wait(self, issue: Issue, task: Task, verdict: Verdict) -> None:
        deps = [n for n in verdict.depends_on if n != issue.number]
        if not deps:
            self.record_failure(issue, task, "returned `waiting` without `depends_on`",
                                status=L.READY if issue.status == L.IN_PROGRESS else None)
            return
        if issue.status == L.IN_PROGRESS:
            self.gh.set_status(issue, L.READY)
        self.gh.edit_labels(issue.number, add=[L.WAITING])
        listed = ", ".join(f"#{n}" for n in deps)
        self.gh.comment(issue.number,
                        f"Waiting for {listed} to close: {verdict.summary}\n"
                        f"<!-- office:depends {','.join(map(str, deps))} -->")
        log.info("#%s waiting on %s", issue.number, listed)

    def file_follow_up(self, source: Issue, title: str, body: str) -> None:
        wanted = normalize_title(title)
        for n, existing in self.gh.open_issue_titles().items():
            if normalize_title(existing) == wanted:
                log.info("#%s: %r is already open as #%s; not filing it again",
                         source.number, title, n)
                return
        labels = [L.TRIAGE]
        if title.lower().startswith("practice:"):
            labels.append(L.PRACTICE)
            if self.cfg.practices_need_approval:
                labels.append(L.BLOCKED)
                body += ("\n\n---\nA suggested practice. To have the office do it, remove "
                         "`blocked:human`. To decline, close this issue.")
        n = self.gh.create_issue(title, f"{body}\n\nSuggested while working on #{source.number}.",
                                 labels)
        log.info("#%s filed #%s: %s", source.number, n, title)

    def file_blocker(self, issue: Issue, verdict: Verdict) -> None:
        blocker = verdict.blocker or {
            "title": f"Decision needed on #{issue.number}",
            "decision": verdict.summary,
        }
        number = self.gh.create_issue(
            f"Decision: {blocker.get('title') or issue.title}",
            blocker_body(blocker, [issue.number]),
            [L.BLOCKER, L.BLOCKED],
        )
        self.gh.edit_labels(issue.number, add=[L.BLOCKED])
        if issue.status == L.IN_PROGRESS:
            self.gh.set_status(issue, L.READY)
        self.gh.comment(issue.number, f"Blocked on #{number}.\n{mark('blocked')}")
        log.info("#%s blocked on #%s", issue.number, number)

    def advance(self, issue: Issue, status: str, verdict: Verdict, prefix: str = "") -> None:
        self.gh.set_status(issue, status)
        head = f"{prefix}. " if prefix else ""
        self.gh.comment(issue.number, f"{head}{verdict.summary}\n\nNext: `{status}`\n"
                                      f"{mark('advance')}")
        log.info("#%s -> %s", issue.number, status)

    def record_failure(self, issue: Issue, task: Task, reason: str,
                       status: str | None = None) -> None:
        if self.stopping.is_set():
            log.info("%s on #%s interrupted by shutdown; not counted as a failure",
                     task.kind, issue.number)
            return
        count = planner.failures(issue) + 1
        log.warning("%s on #%s failed (%s/%s): %s", task.kind, issue.number, count, MAX_FAILURES,
                    reason)
        if status:
            self.gh.set_status(issue, status)
        self.gh.comment(issue.number, f"The {task.role or 'office'} could not finish "
                                      f"({count}/{MAX_FAILURES}): {reason[-1500:]}\n{FAILED_MARK}")
        if count >= MAX_FAILURES:
            self.file_blocker(issue, Verdict(
                outcome="blocked",
                summary=f"{task.kind} failed {count} times",
                blocker={
                    "title": f"#{issue.number} keeps failing",
                    "decision": f"The office failed to {task.kind} #{issue.number} {count} times. "
                                "How should it proceed?",
                    "context": f"Last error: {reason[-1000:]}",
                    "options": [
                        "Clarify the issue, then remove `blocked:human`",
                        "Fix the environment problem, then remove `blocked:human`",
                        "Close the issue",
                    ],
                    "recommendation": "Read the failure comments on the issue.",
                },
            ))
