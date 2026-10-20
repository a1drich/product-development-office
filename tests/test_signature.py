import subprocess
import sys

from office import ghshim
from office.ghshim import sign_args
from office.planner import FAILED_MARK, failures
from office.signature import MARK, footer, is_signed, sign


def no_file(path):
    raise AssertionError(f"unexpected read of {path}")


def test_sign_adds_one_visible_and_one_hidden_signature():
    signed = sign("Looks good.", "reviewer", 12)
    assert "🤖 Reviewer (Codex)" in signed and f"{MARK} role=reviewer issue=12 -->" in signed
    assert sign(signed, "reviewer", 12) == signed  # never twice


def test_the_marker_is_not_an_orchestrator_state_mark():
    # The planner treats any `<!-- office:` comment as progress, which resets the
    # failure count; agent comments must not.
    assert "<!-- office:" not in footer("tester", 3)


def test_agent_comments_between_failures_do_not_reset_the_count():
    from datetime import UTC, datetime

    from office.gh import Comment, Issue

    now = datetime.now(UTC)
    issue = Issue(1, "x", "", set(), comments=[
        Comment("o", FAILED_MARK, now), Comment("o", sign("Test report", "tester", 1), now),
        Comment("o", FAILED_MARK, now)])
    assert failures(issue) == 2


def test_signs_an_inline_body():
    for form in (["--body", "Done"], ["-b", "Done"], ["--body=Done"]):
        args, stdin = sign_args(["pr", "comment", "5", *form], "tester", "7", no_file, None)
        assert stdin is None
        assert args[:3] == ["pr", "comment", "5"] and is_signed(args[-1])


def test_signs_a_body_file_or_stdin_and_passes_it_on_stdin():
    args, stdin = sign_args(["issue", "comment", "7", "--body-file", "notes.md"], "designer",
                            "7", lambda p: "## Design", None)
    assert args == ["issue", "comment", "7", "--body-file", "-"]
    assert stdin.startswith("## Design") and is_signed(stdin)
    args, stdin = sign_args(["pr", "create", "--title", "T", "-F", "-"], "engineer", "7",
                            no_file, lambda: "Closes #7")
    assert args == ["pr", "create", "--title", "T", "--body-file", "-"] and is_signed(stdin)


def test_leaves_other_commands_and_edits_alone():
    for argv in (["issue", "edit", "7", "--body", "x"], ["pr", "view", "5"],
                 ["pr", "create", "--fill"]):
        assert sign_args(argv, "pm", "7", no_file, None) == (argv, None)


def test_the_installed_wrapper_signs_and_runs_the_real_gh(tmp_path):
    fake = tmp_path / "real-gh"
    fake.write_text(f"#!{sys.executable}\nimport sys\n"
                    "print(repr(sys.argv[1:]))\nprint(sys.stdin.read())\n")
    fake.chmod(0o755)
    shim = ghshim.install(tmp_path / "bin") / "gh"
    env = {"OFFICE_REAL_GH": str(fake), "OFFICE_AGENT_ROLE": "tester", "OFFICE_ISSUE": "9",
           "PATH": "/usr/bin:/bin"}
    out = subprocess.run([str(shim), "pr", "comment", "5", "--body-file", "-"], env=env,
                         input="All criteria pass.", capture_output=True, text=True,
                         check=True).stdout
    assert "'--body-file', '-'" in out and "All criteria pass." in out
    assert "🤖 Tester (Codex)" in out and "role=tester issue=9" in out
    # Without a role (not an agent run), it passes everything through untouched.
    out = subprocess.run([str(shim), "pr", "comment", "5", "--body", "hi"],
                         env={**env, "OFFICE_AGENT_ROLE": ""}, capture_output=True,
                         text=True, check=True).stdout
    assert "'--body', 'hi'" in out and "🤖" not in out


def test_agents_cannot_give_the_owners_approval_labels(monkeypatch, capsys):
    assert ghshim.approval_in(["issue", "edit", "4", "--add-label", "release:approved"])
    assert ghshim.approval_in(["api", "repos/o/r/issues/4/labels",
                               "-f", "labels[]=rollback:approved"])
    assert ghshim.approval_in(["issue", "comment", "4", "--body", "add release:approved"]) is None
    monkeypatch.setenv("OFFICE_AGENT_ROLE", "tester")
    monkeypatch.setenv("OFFICE_REAL_GH", "/bin/false-gh-never-run")
    assert ghshim.main(["issue", "edit", "4", "--add-label", "release:approved"]) == 1
    assert "owner's approval" in capsys.readouterr().err
