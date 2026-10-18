import pytest

from office import workspace
from office.shell import CommandError, Result
from office.workspace import Workspace


def fake_run(results):
    calls = []

    def run(args, cwd=None, check=True, **kw):
        calls.append(args)
        return results.pop(0)

    return run, calls


def test_git_retries_ref_lock_contention(tmp_path, monkeypatch):
    lock = Result(1, "", "error: cannot lock ref 'refs/remotes/origin/main'")
    run, calls = fake_run([lock, lock, Result(0, "ok", "")])
    monkeypatch.setattr(workspace, "run", run)
    monkeypatch.setattr(workspace.time, "sleep", lambda s: None)
    res = Workspace("o/r", tmp_path).git("fetch", "origin")
    assert res.ok and len(calls) == 3


def test_git_does_not_retry_other_errors(tmp_path, monkeypatch):
    run, calls = fake_run([Result(128, "", "fatal: not a git repository")])
    monkeypatch.setattr(workspace, "run", run)
    with pytest.raises(CommandError):
        Workspace("o/r", tmp_path).git("status")
    assert len(calls) == 1
