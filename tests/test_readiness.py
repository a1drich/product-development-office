from office import labels as L
from office.readiness import FAIL, PASS, WARN, check_files, check_github, verify_command, worst


def levels(root):
    return {f.key: f.level for f in check_files(root)}


def test_empty_repo_fails(tmp_path):
    found = levels(tmp_path)
    assert found["agents-md"] == FAIL
    assert found["verify"] == FAIL
    assert found["impeccable"] == FAIL
    assert worst(check_files(tmp_path)) == FAIL


def test_ready_repo_passes(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# brief")
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE.md\n\n@AGENTS.md\n")
    (tmp_path / "Makefile").write_text("lint:\n\techo\n\nverify: lint\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "decisions.md").write_text("x")
    (tmp_path / "PRODUCT.md").write_text("x")
    (tmp_path / "DESIGN.md").write_text("x")
    (tmp_path / ".claude" / "skills" / "impeccable").mkdir(parents=True)
    (tmp_path / ".env.example").write_text("")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("")
    assert worst(check_files(tmp_path)) == PASS


def test_claude_md_only_is_a_warning(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# lots of guidance")
    assert levels(tmp_path)["agents-md"] == WARN


def test_separate_claude_and_agents_md_warns(tmp_path):
    (tmp_path / "AGENTS.md").write_text("a")
    (tmp_path / "CLAUDE.md").write_text("b")
    assert levels(tmp_path)["claude-md"] == WARN


def test_verify_command_detection(tmp_path):
    assert verify_command(tmp_path) is None
    (tmp_path / "package.json").write_text('{"scripts": {"verify": "./scripts/verify.sh"}}')
    assert verify_command(tmp_path) == "npm run verify"
    (tmp_path / "Makefile").write_text("verify: lint test\n")
    assert verify_command(tmp_path) == "make verify"


def test_github_checks():
    all_labels = {lb.name for lb in L.LABELS}
    ok = {f.key: f.level for f in check_github({"hasIssuesEnabled": True}, all_labels)}
    assert ok == {"issues": PASS, "labels": PASS}
    bad = {f.key: f.level for f in check_github({"hasIssuesEnabled": False}, set())}
    assert bad == {"issues": FAIL, "labels": WARN}
