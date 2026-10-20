"""`office` command line: check, labels, start, release and the rest."""

from __future__ import annotations

import argparse
import logging
import re
import sys

from office import auth, readiness
from office import labels as L
from office.config import Config
from office.gh import GitHub
from office.orchestrator import Office
from office.readiness import FAIL, PASS, WARN
from office.shell import CommandError, run
from office.workspace import Workspace

REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
ICONS = {PASS: "✓", WARN: "!", FAIL: "✗"}


def resolve_repo(arg: str | None, cfg: Config) -> str:
    repo = arg or cfg.repo
    while not repo:
        repo = input("? Which GitHub repo should the office work on? (owner/name) ").strip()
    if not REPO_RE.match(repo):
        sys.exit(f"not a GitHub repo: {repo!r} (expected owner/name)")
    if repo != cfg.repo:
        cfg.repo = repo
        cfg.save()
    return repo


def print_checks(checks: list[auth.Check]) -> bool:
    for c in checks:
        print(f"{'✓' if c.ok else '✗'} {c.name}: {c.detail}")
    return all(c.ok for c in checks)


def cmd_check(args: argparse.Namespace, cfg: Config) -> int:
    repo = resolve_repo(args.repo, cfg)
    if not print_checks([auth.check_gh()]):
        return 1
    gh = GitHub(repo)
    ws = Workspace(repo)
    print(f"→ reading {repo} into {ws.clone}")
    ws.ensure_clone()
    ws.update_default_branch()

    findings = readiness.check_files(ws.clone)
    findings += readiness.check_github(gh.repo_info(), gh.label_names())

    if args.run_verify:
        cmd = readiness.verify_command(ws.clone)
        if cmd:
            print(f"→ running `{cmd}` (this can take a while)")
            res = run(cmd.split(), cwd=ws.clone, check=False, timeout=3600)
            if res.ok:
                findings.append(readiness.Finding("verify-run", PASS, f"`{cmd}` passes"))
            else:
                tail = (res.stdout + res.stderr).strip()[-1500:]
                findings.append(readiness.Finding(
                    "verify-run", FAIL, f"`{cmd}` fails on a fresh clone",
                    f"Make it pass from a fresh clone with no manual steps.\n\n```\n{tail}\n```",
                ))

    print()
    for f in findings:
        print(f"{ICONS[f.level]} {f.summary}")
        if f.level != PASS and f.fix:
            print(f"    {f.fix.splitlines()[0]}")
    overall = readiness.worst(findings)
    verdict = {PASS: "ready", WARN: "ready with warnings", FAIL: "not ready"}[overall]
    print(f"\n{repo}: {verdict}")

    if args.file_issues:
        todo = [f for f in findings if f.level != PASS]
        if todo:
            gh.ensure_labels()
            for f in todo:
                if gh.find_issue_by_title(f.issue_title):
                    print(f"  already filed: {f.issue_title}")
                    continue
                n = gh.create_issue(f.issue_title, f"{f.fix}\n\nFound by `office check`.",
                                    [L.TRIAGE])
                print(f"  filed #{n}: {f.issue_title}")
    return 1 if overall == FAIL else 0


def cmd_labels(args: argparse.Namespace, cfg: Config) -> int:
    repo = resolve_repo(args.repo, cfg)
    created = GitHub(repo).ensure_labels()
    print(f"created {len(created)} labels" + (f": {', '.join(created)}" if created else ""))
    return 0


def cmd_start(args: argparse.Namespace, cfg: Config) -> int:
    repo = resolve_repo(args.repo, cfg)
    if not print_checks(auth.preflight()):
        print("\nfix the checks above, then run `office start` again")
        return 1
    gh = GitHub(repo)
    ws = Workspace(repo)
    ws.ensure_clone()
    ws.update_default_branch()
    print(f"✓ cloned {repo} into {ws.clone}")
    if args.dry_run:
        missing = {lb.name for lb in L.LABELS} - gh.label_names()
        print(f"→ dry run: {len(missing)} labels would be created; nothing will change")
    else:
        created = gh.ensure_labels()
        print(f"✓ labels ready ({len(created)} created)")
    office = Office(cfg, gh, ws, dry_run=args.dry_run)
    print(f"→ verify command: {office.verify}")
    if not args.dry_run:
        print("→ Ctrl-C (or `office stop`) stops after running agents finish; "
              "press it twice (or `office stop --now`) to stop immediately")
    office.run(exit_when_idle=args.exit_when_idle)
    if not args.dry_run:
        print("stopped. Run `office start` again to pick up where it left off.")
    return 0


def cmd_stop(args: argparse.Namespace, cfg: Config) -> int:
    import os
    import signal
    import time

    repo = args.repo or cfg.repo
    if not repo or not REPO_RE.match(repo):
        sys.exit("which repo? `office stop owner/name`")
    ws = Workspace(repo)
    pid = ws.running_pid()
    if not pid:
        print(f"no office is running on {repo}")
        return 0
    if args.now:
        os.kill(pid, signal.SIGTERM)
        print(f"stopping the office on {repo} now (pid {pid})")
    else:
        os.kill(pid, signal.SIGINT)
        print(f"draining the office on {repo} (pid {pid}): it starts nothing new and exits "
              "once running agents finish. `office stop --now` stops it immediately.")
    if args.no_wait:
        return 0
    while ws.running_pid() == pid:
        time.sleep(2)
    print("stopped")
    return 0


def cmd_shoot(args: argparse.Namespace, cfg: Config) -> int:
    from pathlib import Path

    from office import shoot

    pages = shoot.load_pages(Path(args.pages))
    shots = shoot.shoot(args.base_url, pages, Path(args.out))
    print(shoot.report(shots))
    failed = [s for s in shots if s.problems]
    print(f"\n{len(shots)} screenshot(s) in {args.out}; {len(failed)} with problems")
    return 1 if failed else 0


def cmd_plan(args: argparse.Namespace, cfg: Config) -> int:
    from datetime import UTC, datetime, timedelta

    from office import plan
    from office.ports import Leases

    repo = args.repo or cfg.repo
    if not repo or not REPO_RE.match(repo):
        sys.exit("which repo? `office plan owner/name`")
    rows = plan.describe(GitHub(repo).open_issues(), datetime.now(UTC),
                         timedelta(minutes=cfg.claim_ttl_minutes))
    print(f"{repo}\n")
    print(plan.render(rows, cfg.limits))
    leases = Leases(Workspace(repo).leases, cfg.agent_ports, cfg.ports_per_agent,
                    cfg.reserved_ports, cfg.fixed_ports)
    print("\n" + plan.render_leases(leases.table()))
    return 0


def cmd_release(args: argparse.Namespace, cfg: Config) -> int:
    """Approves the open release (or, with --rollback, its rollback) by adding the
    approval label as you. The running office does the rest, as if you added it on GitHub."""
    from office import planner

    repo = args.repo or cfg.repo
    if not repo or not REPO_RE.match(repo):
        sys.exit("which repo? `office release owner/name`")
    gh = GitHub(repo)
    releases = gh.labelled_issues(L.RELEASE)
    if args.rollback:
        todo = [i for i in releases if planner.deployed(i) and i.status != L.TESTING]
        label, verb = L.ROLLBACK_APPROVED, "roll back"
    else:
        todo = [i for i in releases if not planner.deployed(i)]
        label, verb = L.RELEASE_APPROVED, "release"
    if not todo:
        print(f"{repo} has no release waiting to {verb}")
        return 0
    issue = todo[0]
    if label in issue.labels:
        print(f"#{issue.number} is already approved; the running office picks it up")
        return 0
    print(f"#{issue.number} {issue.title}: https://github.com/{repo}/issues/{issue.number}\n")
    print("\n".join(re.findall(r"^- #\d+ .*$", issue.body, re.M)) or "(no changes listed)")
    if not args.yes and input(f"\n{verb.capitalize()} this? [y/N] ").strip().lower() != "y":
        print("nothing changed")
        return 1
    gh.edit_labels(issue.number, add=[label])
    print(f"✓ added `{label}` to #{issue.number}. The office runs it on its next pass "
          "(start it if it isn't running), and reports on the issue.")
    return 0


def cmd_clean(args: argparse.Namespace, cfg: Config) -> int:
    from office import clean

    repo = args.repo or cfg.repo
    if not repo or not REPO_RE.match(repo):
        sys.exit("which repo? `office clean owner/name`")
    ws = Workspace(repo)
    ws.migrate_legacy()
    busy = clean.running_in(ws)
    if busy:
        print(f"✗ the office or its agents are still running in {repo}'s folders "
              f"(pids {', '.join(map(str, sorted(busy)))}). Stop them first.")
        return 1

    if args.github:
        gh = GitHub(repo)
        plan = clean.plan_github(gh)
        print(f"On GitHub ({repo}):")
        print(f"  delete {len(plan.labels)} office labels")
        print(f"  delete {len(plan.branches)} office branches without an open PR")
        for b in plan.kept_branches:
            print(f"  keep {b}: it has an open PR (close the PR first to remove it)")
        if plan.status_issue:
            print(f"  close the status issue #{plan.status_issue}")
        if not plan.empty:
            if not args.yes and input("Proceed? [y/N] ").strip().lower() != "y":
                print("nothing changed")
                return 1
            clean.clean_github(gh, plan)
            print("✓ GitHub cleaned")

    if ws.clone.exists() or cfg.database_url:  # where Postgres is
        from office.databases import Databases

        for name in Databases(ws.clone, repo, cfg.database_url).drop():
            print(f"✓ dropped database {name}")
    removed = clean.clean_local(ws, cfg)
    for r in removed:
        print(f"✓ removed {r}")
    if not removed:
        print(f"nothing local to remove for {repo}")
    return 0


MKDOCS = ["uvx", "--with", "mkdocs-material", "mkdocs"]


def cmd_docs(args: argparse.Namespace, cfg: Config) -> int:
    repo = resolve_repo(args.repo, cfg)
    ws = Workspace(repo)
    ws.ensure_clone()
    ws.update_default_branch()
    if not (ws.clone / "mkdocs.yml").exists():
        print(f"{repo} has no mkdocs.yml yet; see docs/INTEGRATION.md, step 4")
        return 1
    if args.action == "build":
        res = run([*MKDOCS, "build", "--strict"], cwd=ws.clone, check=False, timeout=600)
        print((res.stdout + res.stderr).strip()[-3000:])
        return 0 if res.ok else 1
    print(f"→ serving {repo}'s docs at http://127.0.0.1:{args.port} (Ctrl-C to stop)")
    import subprocess

    try:
        return subprocess.call([*MKDOCS, "serve", "-a", f"127.0.0.1:{args.port}"],
                               cwd=ws.clone)
    except KeyboardInterrupt:
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="office", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="check whether a repo is ready for the office")
    p.add_argument("repo", nargs="?")
    p.add_argument("--run-verify", action="store_true",
                   help="also run the repo's verify command on the fresh clone")
    p.add_argument("--file-issues", action="store_true",
                   help="file an issue for every failed or warned check")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("labels", help="create the office labels on a repo")
    p.add_argument("repo", nargs="?")
    p.set_defaults(fn=cmd_labels)

    p = sub.add_parser("start", help="run the office on a repo until it is blocked")
    p.add_argument("repo", nargs="?")
    p.add_argument("--dry-run", action="store_true",
                   help="print what the office would do, without changing anything")
    p.add_argument("--exit-when-idle", action="store_true",
                   help="exit instead of polling when every issue is blocked or done")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("shoot", help="screenshot and UX-check a running app's manual pages")
    p.add_argument("--base-url", required=True, help="where the app is running")
    p.add_argument("--pages", default="docs/manual/pages.json")
    p.add_argument("--out", default="docs/manual/screenshots")
    p.set_defaults(fn=cmd_shoot)

    p = sub.add_parser("stop", help="stop a running office once its agents finish "
                                    "(--now to stop immediately)")
    p.add_argument("repo", nargs="?")
    p.add_argument("--now", action="store_true", help="end running agents and stop immediately")
    p.add_argument("--no-wait", action="store_true", help="don't wait for the office to exit")
    p.set_defaults(fn=cmd_stop)

    p = sub.add_parser("plan", help="show what the office would do next (read-only; safe while "
                                    "the office runs)")
    p.add_argument("repo", nargs="?")
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("release", help="approve the open release, which the office then runs "
                                       "and checks live (--rollback to approve rolling it back)")
    p.add_argument("repo", nargs="?")
    p.add_argument("--rollback", action="store_true",
                   help="approve rolling back a release whose live check failed")
    p.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    p.set_defaults(fn=cmd_release)

    p = sub.add_parser("clean", help="remove a project's local state (and, optionally, "
                                     "the office's labels, branches and status issue on GitHub)")
    p.add_argument("repo", nargs="?")
    p.add_argument("--github", action="store_true",
                   help="also remove the office's labels, branches and status issue on GitHub")
    p.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    p.set_defaults(fn=cmd_clean)

    p = sub.add_parser("docs", help="build or serve a target repo's MkDocs site")
    p.add_argument("action", choices=["build", "serve"])
    p.add_argument("repo", nargs="?")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(fn=cmd_docs)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return args.fn(args, Config.load())
    except (CommandError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
