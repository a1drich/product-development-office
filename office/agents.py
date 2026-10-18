"""Runs role agents as CLI subprocesses and reads back their verdicts.

PM, Designer and Engineer run on Claude Code; Reviewer and Tester run on Codex. Every
agent ends its work with a JSON verdict. The orchestrator, not the agent, applies label
changes and merges based on that verdict, so the state machine never depends on an
agent remembering to edit a label.
"""

from __future__ import annotations

import json
import os
import re
import signal
import tempfile
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from office.config import Config
from office.shell import clean_env, run

CLAUDE_ROLES = {"pm", "designer", "engineer"}
CODEX_ROLES = {"reviewer", "tester"}

RATE_LIMIT = re.compile(
    r"usage limit|rate limit|limit reached|too many requests|hit your limit|quota", re.I
)

VERDICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["outcome", "summary", "pr", "blocker", "new_issues", "depends_on"],
    "properties": {
        "outcome": {"type": "string"},
        "summary": {"type": "string"},
        "pr": {"type": ["integer", "null"]},
        "blocker": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "decision", "context", "options", "recommendation"],
                    "properties": {
                        "title": {"type": "string"},
                        "decision": {"type": "string"},
                        "context": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "recommendation": {"type": "string"},
                    },
                },
            ]
        },
        "depends_on": {"type": "array", "items": {"type": "integer"}},
        "new_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "body"],
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
            },
        },
    },
}


@dataclass
class Verdict:
    outcome: str
    summary: str = ""
    pr: int | None = None
    blocker: dict | None = None
    new_issues: list[dict] = field(default_factory=list)
    depends_on: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Verdict:
        return cls(
            outcome=str(d.get("outcome", "")).strip().lower(),
            summary=d.get("summary") or "",
            pr=d.get("pr"),
            blocker=d.get("blocker") or None,
            new_issues=d.get("new_issues") or [],
            depends_on=[int(n) for n in d.get("depends_on") or [] if str(n).isdigit()],
        )


@dataclass
class AgentResult:
    role: str
    verdict: Verdict | None
    output: str
    rate_limited: bool = False
    error: str = ""


def render(role: str, values: dict[str, str]) -> str:
    """Fill a role prompt. Placeholders are {{name}}, so issue text with braces is safe."""
    text = resources.files("office.prompts").joinpath(f"{role}.md").read_text()
    for part in ("verdict", "context"):
        shared = resources.files("office.prompts").joinpath(f"_{part}.md").read_text()
        text = text.replace("{{" + part + "}}", shared)
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), m.group(0)), text)


def extract_verdict(text: str) -> Verdict | None:
    """The last JSON object in the text that has an "outcome" key."""
    candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates += re.findall(r"(\{[^{}]*\"outcome\".*\})", text, re.S)
    for raw in reversed(candidates):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "outcome" in data:
            return Verdict.from_dict(data)
    return None


def run_agent(
    role: str, prompt: str, cwd: Path, cfg: Config, exclusive: bool = False
) -> AgentResult:
    """Runs one agent in `cwd`. When the folder is `exclusive` to this agent (an issue's
    worktree), anything it left running there, such as a dev server, is stopped afterwards.
    The shared main clone is never cleaned, since other agents may be working in it."""
    timeout = cfg.agent_timeout_minutes * 60
    try:
        if role in CLAUDE_ROLES:
            return _run_claude(role, prompt, cwd, cfg, timeout)
        if role in CODEX_ROLES:
            return _run_codex(role, prompt, cwd, cfg, timeout)
        raise ValueError(f"unknown role {role}")
    finally:
        if exclusive:
            stop_leftovers(cwd)


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def leftover_pids(root: Path) -> set[int]:
    """Processes an agent left running in its folder, such as dev servers."""
    root_s = str(root.resolve())
    pids: set[int] = set()
    # Processes whose working directory is inside the folder.
    res = run(["lsof", "-a", "-d", "cwd", "-F", "pn"], check=False)
    pid = None
    for line in res.stdout.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and pid and _under(line[1:], root_s):
            pids.add(pid)
    # Processes started from the folder's virtualenv or scripts.
    res = run(["pgrep", "-f", root_s + os.sep], check=False)
    pids |= {int(p) for p in res.stdout.split() if p.isdigit()}
    pids.discard(os.getpid())
    return pids


def stop_leftovers(root: Path) -> None:
    for pid in leftover_pids(root):
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


def _run_claude(role: str, prompt: str, cwd: Path, cfg: Config, timeout: float) -> AgentResult:
    args = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--permission-mode", cfg.claude_permission_mode,
    ]
    res = run(args, cwd=cwd, check=False, timeout=timeout, env=clean_env())
    text = res.stdout
    try:
        payload = json.loads(res.stdout)
        text = payload.get("result") or ""
        if payload.get("is_error") and RATE_LIMIT.search(text):
            return AgentResult(role, None, text, rate_limited=True, error=text)
    except json.JSONDecodeError:
        pass
    return _finish(role, res.returncode, text, res.stderr)


def _run_codex(role: str, prompt: str, cwd: Path, cfg: Config, timeout: float) -> AgentResult:
    sandbox = cfg.codex_sandbox.get(role, "workspace-write")
    with tempfile.TemporaryDirectory() as tmp:
        schema = Path(tmp) / "schema.json"
        schema.write_text(json.dumps(VERDICT_SCHEMA))
        last = Path(tmp) / "last.txt"
        args = [
            "codex", "exec",
            "-C", str(cwd),
            "-s", sandbox,
            "-c", "sandbox_workspace_write.network_access=true",
            "--output-schema", str(schema),
            "-o", str(last),
            prompt,
        ]
        res = run(args, cwd=cwd, check=False, timeout=timeout, env=clean_env())
        text = last.read_text() if last.exists() else ""
    return _finish(role, res.returncode, text or res.stdout, res.stderr)


def _finish(role: str, code: int, text: str, stderr: str) -> AgentResult:
    verdict = extract_verdict(text)
    if verdict:
        return AgentResult(role, verdict, text)
    combined = f"{text}\n{stderr}"
    if RATE_LIMIT.search(combined):
        return AgentResult(role, None, text, rate_limited=True, error=combined.strip()[-500:])
    return AgentResult(role, None, text,
                       error=f"exit {code}, no verdict: {combined.strip()[-500:]}")
