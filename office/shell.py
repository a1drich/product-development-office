"""Subprocess helper. Every external command (gh, git, claude, codex) goes through `run`."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
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


# Every command runs in its own session, so a Ctrl-C in the terminal reaches only the
# office, which decides whether to drain or stop. Live commands are tracked so a hard
# stop can end them, along with anything they started.
_live: set[subprocess.Popen] = set()
_live_lock = threading.Lock()


def _kill_group(proc: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def stop_all(sig: int = signal.SIGTERM) -> int:
    """Signals every command the office is running. Returns how many there were."""
    with _live_lock:
        procs = list(_live)
    for proc in procs:
        _kill_group(proc, sig)
    return len(procs)


def run(
    args: list[str],
    cwd: Path | str | None = None,
    check: bool = True,
    input: str | None = None,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
) -> Result:
    try:
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env if env is not None else clean_env(),
            start_new_session=True,
        )
    except FileNotFoundError:
        result = Result(127, "", f"{args[0]}: command not found")
    else:
        with _live_lock:
            _live.add(proc)
        try:
            out, err = proc.communicate(input=input, timeout=timeout)
            result = Result(proc.returncode, out, err)
        except subprocess.TimeoutExpired:
            _kill_group(proc, signal.SIGKILL)
            out, _ = proc.communicate()
            result = Result(124, out or "", f"timed out after {timeout}s")
        finally:
            with _live_lock:
                _live.discard(proc)
    if check and not result.ok:
        raise CommandError(args, result)
    return result
