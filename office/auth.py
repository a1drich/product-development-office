"""Startup checks: the CLIs exist, are logged in, and use subscriptions, never API keys."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from office.shell import API_KEY_VARS, run


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def check_api_keys() -> Check:
    found = [v for v in API_KEY_VARS if os.environ.get(v)]
    if found:
        names = ", ".join(found)
        return Check("no API keys", False, f"unset {names}: the office uses subscriptions only")
    return Check("no API keys", True, "none set")


def check_gh() -> Check:
    res = run(["gh", "auth", "status", "--active"], check=False)
    if not res.ok:
        return Check("gh", False, "not logged in: run `gh auth login`")
    return Check("gh", True, "logged in")


def parse_claude_status(text: str) -> Check:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return Check("claude", False, "could not read `claude auth status`")
    if not data.get("loggedIn"):
        return Check("claude", False, "not logged in: run `claude` then /login")
    if data.get("authMethod") != "claude.ai":
        return Check(
            "claude", False,
            f"uses {data.get('authMethod')!r} auth; log in with a Claude subscription instead",
        )
    plan = data.get("subscriptionType") or "subscription"
    return Check("claude", True, f"logged in ({plan})")


def check_claude() -> Check:
    res = run(["claude", "auth", "status"], check=False)
    if res.returncode == 127:
        return Check("claude", False, "Claude Code is not installed")
    return parse_claude_status(res.stdout)


def parse_codex_status(text: str) -> Check:
    if "ChatGPT" in text:
        return Check("codex", True, "logged in (ChatGPT)")
    if "API key" in text:
        return Check("codex", False, "uses an API key; run `codex login` and sign in with ChatGPT")
    return Check("codex", False, "not logged in: run `codex login`")


def check_codex() -> Check:
    res = run(["codex", "login", "status"], check=False)
    if res.returncode == 127:
        return Check("codex", False, "Codex CLI is not installed")
    return parse_codex_status(res.stdout + res.stderr)


def preflight() -> list[Check]:
    return [check_api_keys(), check_gh(), check_claude(), check_codex()]
