import json

import pytest

from office.agents import VERDICT_SCHEMA, _finish, extract_verdict, render
from office.auth import parse_claude_status, parse_codex_status
from office.shell import clean_env


def test_extract_verdict_from_fenced_block():
    text = 'Done.\n\n```json\n{"outcome": "Ready", "summary": "ok", "pr": null, ' \
           '"blocker": null, "new_issues": []}\n```'
    v = extract_verdict(text)
    assert v.outcome == "ready"
    assert v.summary == "ok"


def test_extract_verdict_takes_the_last_one():
    text = (
        '```json\n{"outcome": "failed", "summary": "first"}\n```\n'
        'retried\n```json\n{"outcome": "opened", "summary": "second", "pr": 7}\n```'
    )
    v = extract_verdict(text)
    assert (v.outcome, v.pr) == ("opened", 7)


def test_extract_verdict_from_bare_json():
    assert extract_verdict('{"outcome": "pass", "summary": "s"}').outcome == "pass"


def test_no_verdict():
    assert extract_verdict("I could not finish") is None


def test_rate_limit_without_verdict_is_flagged():
    r = _finish("engineer", 1, "", "Claude usage limit reached. Resets at 5pm.")
    assert r.rate_limited and r.verdict is None


def test_failure_without_verdict_has_error():
    r = _finish("tester", 1, "crashed", "")
    assert not r.rate_limited and "no verdict" in r.error


@pytest.mark.parametrize(
    "role", ["pm", "pm_blocker", "pm_practices", "designer", "engineer", "reviewer", "tester"]
)
def test_prompts_render_without_leftover_placeholders(role):
    values = {k: "X" for k in
              ["repo", "number", "title", "body", "comments", "verify", "branch", "base", "pr",
               "pr_context", "findings", "open_practices", "max_new", "shoot",
               "docs_build"]}
    text = render(role, values)
    assert "{{" not in text
    assert '"outcome"' in text  # the shared verdict instructions are included
    assert "Two contexts, kept separate" in text
    assert "Practice: " in text


def test_issue_text_with_braces_is_safe():
    text = render("pm", {"body": "use {{repo}} and {x}", "repo": "o/r"})
    assert "use {{repo}} and {x}" in text


def test_designer_uses_impeccable():
    assert "impeccable" in render("designer", {})


def test_schema_is_strict():
    assert VERDICT_SCHEMA["additionalProperties"] is False
    assert set(VERDICT_SCHEMA["required"]) == set(VERDICT_SCHEMA["properties"])
    json.dumps(VERDICT_SCHEMA)


def test_claude_auth_parsing():
    sub = parse_claude_status('{"loggedIn": true, "authMethod": "claude.ai", '
                              '"subscriptionType": "max"}')
    assert sub.ok and "max" in sub.detail
    key = parse_claude_status('{"loggedIn": true, "authMethod": "apiKey"}')
    assert not key.ok
    assert not parse_claude_status('{"loggedIn": false}').ok
    assert not parse_claude_status("garbage").ok


def test_codex_auth_parsing():
    assert parse_codex_status("Logged in using ChatGPT").ok
    assert not parse_codex_status("Logged in using an API key - sk-...").ok
    assert not parse_codex_status("Not logged in").ok


def test_clean_env_strips_api_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
    env = clean_env()
    assert "ANTHROPIC_API_KEY" not in env and "OPENAI_API_KEY" not in env


def test_leftover_pids_finds_a_process_started_in_the_folder(tmp_path):
    import subprocess
    import sys
    import time

    from office.agents import leftover_pids, stop_leftovers

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=tmp_path)
    try:
        time.sleep(0.3)
        assert proc.pid in leftover_pids(tmp_path)
        stop_leftovers(tmp_path)
        assert proc.wait(timeout=5) != 0
    finally:
        proc.kill()


def test_leftover_pids_ignores_sibling_folders(tmp_path):
    from office.agents import _under

    assert _under("/w/app/sub", "/w/app")
    assert not _under("/w/app-worktrees/issue-1", "/w/app")
