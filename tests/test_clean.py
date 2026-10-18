import subprocess

from office import clean
from office import labels as L
from office.config import Config
from office.workspace import Workspace, folder_name


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_folder_names_include_the_owner(tmp_path):
    a, b = Workspace("acme/web", tmp_path), Workspace("other/web", tmp_path)
    assert folder_name("acme/web") == "acme__web"
    assert a.clone != b.clone and a.worktrees != b.worktrees and a.docs_log != b.docs_log


def make_legacy(tmp_path, origin):
    legacy = tmp_path / "web"
    legacy.mkdir()
    git("init", "-q", "-b", "main", cwd=legacy)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x",
        cwd=legacy)
    git("remote", "add", "origin", origin, cwd=legacy)
    trees = tmp_path / "web-worktrees"
    trees.mkdir()
    git("worktree", "add", "-q", "-b", "office/issue-1", str(trees / "issue-1"), cwd=legacy)
    (trees / "issue-1" / "wip.txt").write_text("uncommitted work")
    (tmp_path / "web-mkdocs.log").write_text("log")
    return legacy


def test_legacy_folder_is_migrated_with_its_worktrees(tmp_path):
    make_legacy(tmp_path, "https://github.com/acme/web.git")
    ws = Workspace("acme/web", tmp_path)
    assert ws.migrate_legacy()
    assert (ws.clone / ".git").exists() and not (tmp_path / "web").exists()
    tree = ws.worktrees / "issue-1"
    assert (tree / "wip.txt").read_text() == "uncommitted work"
    status = subprocess.run(["git", "status", "--short"], cwd=tree, capture_output=True,
                            text=True)
    assert status.returncode == 0  # the worktree link was repaired
    assert ws.docs_log.exists()


def test_legacy_folder_for_another_owner_is_left_alone(tmp_path):
    make_legacy(tmp_path, "https://github.com/other/web.git")
    ws = Workspace("acme/web", tmp_path)
    assert not ws.migrate_legacy()
    assert (tmp_path / "web").exists()


def test_clean_local_removes_folders_and_forgets_the_repo(tmp_path, monkeypatch):
    ws = Workspace("acme/web", tmp_path)
    for p in (ws.clone, ws.worktrees):
        p.mkdir()
    ws.docs_log.write_text("log")
    other = Workspace("acme/api", tmp_path)
    other.clone.mkdir()
    cfg = Config(repo="acme/web", limits={"engineer": 2})
    monkeypatch.setattr(Config, "save", lambda self: None)
    removed = clean.clean_local(ws, cfg)
    assert not any(p.exists() for p in ws.paths)
    assert other.clone.exists()
    assert cfg.repo is None and cfg.limits["engineer"] == 2
    assert len(removed) == 4


class FakeGitHub:
    def __init__(self):
        self.deleted_labels, self.deleted_branches, self.closed = [], [], []

    def label_names(self):
        return {L.READY, L.BLOCKED, "bug", "blocked"}

    def open_pr_branches(self):
        return {"office/issue-2"}

    def office_branches(self):
        return ["office/issue-1", "office/issue-2"]

    def find_issue_by_title(self, title, label=None):
        return 8

    def delete_label(self, name):
        self.deleted_labels.append(name)

    def delete_branch(self, branch):
        self.deleted_branches.append(branch)

    def close_issue(self, n, comment=None):
        self.closed.append(n)


def test_github_clean_keeps_repo_labels_and_branches_with_open_prs():
    gh = FakeGitHub()
    plan = clean.plan_github(gh)
    assert plan.labels == sorted([L.BLOCKED, L.READY])  # not the repo's own "bug" or "blocked"
    assert plan.branches == ["office/issue-1"] and plan.kept_branches == ["office/issue-2"]
    clean.clean_github(gh, plan)
    assert gh.deleted_branches == ["office/issue-1"] and gh.closed == [8]


def test_legacy_folder_in_use_is_not_moved(tmp_path):
    import sys

    import pytest

    legacy = make_legacy(tmp_path, "https://github.com/acme/web.git")
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=legacy)
    try:
        import time

        time.sleep(0.3)
        with pytest.raises(RuntimeError, match="still in use"):
            Workspace("acme/web", tmp_path).migrate_legacy()
        assert legacy.exists()
    finally:
        proc.kill()
