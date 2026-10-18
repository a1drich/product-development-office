"""Thin adapter over the `gh` CLI. The orchestrator touches GitHub only through this class."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from office import labels as L
from office.shell import run


@dataclass
class Comment:
    author: str
    body: str
    created_at: datetime


@dataclass
class Issue:
    number: int
    title: str
    body: str
    labels: set[str]
    state: str = "OPEN"
    comments: list[Comment] = field(default_factory=list)

    @property
    def status(self) -> str | None:
        for s in L.STATUSES:
            if s in self.labels:
                return s
        return None

    @property
    def blocked(self) -> bool:
        return bool(self.labels & ({L.BLOCKED} | L.BLOCKED_ALIASES))

    @property
    def is_blocker(self) -> bool:
        return L.BLOCKER in self.labels


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _issue(data: dict) -> Issue:
    return Issue(
        number=data["number"],
        title=data["title"],
        body=data.get("body") or "",
        labels={lb["name"] for lb in data.get("labels", [])},
        state=data.get("state", "OPEN"),
        comments=[
            Comment(
                author=(c.get("author") or {}).get("login", ""),
                body=c.get("body") or "",
                created_at=_parse_time(c["createdAt"]),
            )
            for c in data.get("comments", [])
        ],
    )


class GitHub:
    def __init__(self, repo: str):
        self.repo = repo

    def _gh(self, *args: str, input: str | None = None, check: bool = True):
        return run(["gh", *args, "--repo", self.repo], input=input, check=check)

    def _gh_json(self, *args: str):
        return json.loads(self._gh(*args).stdout or "null")

    # --- repo -------------------------------------------------------------------

    def repo_info(self) -> dict:
        # `gh repo view` takes the repo as an argument and rejects --repo.
        res = run(["gh", "repo", "view", self.repo, "--json",
                   "hasIssuesEnabled,defaultBranchRef,visibility"])
        return json.loads(res.stdout)

    def label_names(self) -> set[str]:
        data = self._gh_json("label", "list", "--limit", "500", "--json", "name")
        return {d["name"] for d in data}

    def ensure_labels(self) -> list[str]:
        existing = self.label_names()
        created = []
        for label in L.LABELS:
            if label.name not in existing:
                self._gh(
                    "label", "create", label.name,
                    "--color", label.color, "--description", label.description,
                )
                created.append(label.name)
        return created

    # --- issues -----------------------------------------------------------------

    def open_issues(self) -> list[Issue]:
        data = self._gh_json(
            "issue", "list", "--state", "open", "--limit", "500",
            "--json", "number,title,body,labels,state,comments",
        )
        return [_issue(d) for d in data]

    def issue(self, number: int) -> Issue:
        return _issue(
            self._gh_json(
                "issue", "view", str(number), "--json", "number,title,body,labels,state,comments"
            )
        )

    def create_issue(self, title: str, body: str, labels: list[str]) -> int:
        args = ["issue", "create", "--title", title, "--body-file", "-"]
        for lb in labels:
            args += ["--label", lb]
        url = self._gh(*args, input=body).stdout.strip()
        return int(url.rstrip("/").rsplit("/", 1)[-1])

    def comment(self, number: int, body: str) -> None:
        self._gh("issue", "comment", str(number), "--body-file", "-", input=body)

    def edit_labels(self, number: int, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:
        args = ["issue", "edit", str(number)]
        for lb in add:
            args += ["--add-label", lb]
        for lb in remove:
            args += ["--remove-label", lb]
        if len(args) > 3:
            self._gh(*args)

    def set_status(self, issue: Issue, status: str) -> None:
        stale = [s for s in L.STATUSES if s in issue.labels and s != status]
        self.edit_labels(issue.number, add=[status], remove=stale)
        issue.labels = (issue.labels - set(stale)) | {status}

    def edit_body(self, number: int, body: str) -> None:
        self._gh("issue", "edit", str(number), "--body-file", "-", input=body)

    def assign_self(self, number: int) -> None:
        self._gh("issue", "edit", str(number), "--add-assignee", "@me", check=False)

    def close_issue(self, number: int, comment: str | None = None) -> None:
        args = ["issue", "close", str(number)]
        if comment:
            args += ["--comment", comment]
        self._gh(*args)

    def find_issue_by_title(self, title: str, label: str | None = None) -> int | None:
        args = ["issue", "list", "--state", "open", "--search", f'"{title}" in:title',
                "--json", "number,title"]
        if label:
            args += ["--label", label]
        for d in self._gh_json(*args):
            if d["title"] == title:
                return d["number"]
        return None

    # --- pull requests ----------------------------------------------------------

    def pr_for_issue(self, number: int) -> dict | None:
        """The open PR whose branch the office created for this issue."""
        data = self._gh_json(
            "pr", "list", "--state", "open", "--head", branch_name(number),
            "--json", "number,headRefName,url,isDraft",
        )
        return data[0] if data else None

    def pr_checks_passing(self, pr: int) -> tuple[bool, str]:
        res = self._gh("pr", "checks", str(pr), check=False)
        # gh exits 0 when every check passed, 8 when some are pending, 1 on failure.
        # A repo with no CI reports "no checks reported", which counts as passing.
        if res.ok or "no checks reported" in (res.stderr + res.stdout):
            return True, ""
        return False, (res.stdout or res.stderr).strip()

    def merge_pr(self, pr: int) -> None:
        self._gh("pr", "merge", str(pr), "--squash", "--delete-branch")

    def pr_comment(self, pr: int, body: str) -> None:
        self._gh("pr", "comment", str(pr), "--body-file", "-", input=body)


def branch_name(issue_number: int) -> str:
    return f"office/issue-{issue_number}"
