"""Subprocess helper. Every external command (gh, git, claude, codex) goes through `run`."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Never let an agent, or gh, bill an API account: the office runs on subscriptions only.
API_KEY_VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN")


class CommandError(RuntimeError):
    def __init__(self, args: list[str], result: Result):
        self.result = result
        detail = (result.stderr or result.stdout).strip()
        super().__init__(f"{' '.join(args)} exited {result.returncode}: {detail[-2000:]}")


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in API_KEY_VARS}
    if extra:
        env.update(extra)
    return env


def run(
    args: list[str],
    cwd: Path | str | None = None,
    check: bool = True,
    input: str | None = None,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
) -> Result:
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            input=input,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env if env is not None else clean_env(),
        )
    except FileNotFoundError:
        result = Result(127, "", f"{args[0]}: command not found")
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        result = Result(124, out, f"timed out after {timeout}s")
    else:
        result = Result(proc.returncode, proc.stdout, proc.stderr)
    if check and not result.ok:
        raise CommandError(args, result)
    return result
