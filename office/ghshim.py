"""A `gh` wrapper on every agent's PATH that signs what the agent posts, and the
installer for the agents' commands.

Agents post comments, PRs and issues with `gh` themselves. The office puts this wrapper
first on their PATH, with `OFFICE_AGENT_ROLE`, `OFFICE_ISSUE` and `OFFICE_REAL_GH` in
their environment. It adds the role's signature to the body of the commands below and
runs the real `gh` with everything else unchanged. Edits are left alone, so an issue
body the PM rewrites doesn't collect a signature on every pass. It refuses any command
that names a release or rollback approval label: only the owner gives those.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from office.config import ROOT
from office.labels import APPROVALS
from office.signature import sign

SIGNED = {("issue", "comment"), ("pr", "comment"), ("pr", "create"), ("pr", "review"),
          ("issue", "create")}
BIN = ROOT / ".office" / "bin"


def sign_args(
    argv: list[str], role: str, issue: str | None, read_file: Callable[[str], str],
    read_stdin: Callable[[], str],
) -> tuple[list[str], str | None]:
    """The arguments with the body signed, and the text to send on stdin (if any).
    A body given in a file or on stdin is signed and passed on stdin instead."""
    if tuple(argv[:2]) not in SIGNED:
        return argv, None
    out: list[str] = []
    stdin: str | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        flag, eq, inline = arg.partition("=")
        if flag in ("--body", "-b"):
            value = inline if eq else (argv[i + 1] if i + 1 < len(argv) else "")
            out += [flag, sign(value, role, issue)]
            i += 1 if eq else 2
            continue
        if flag in ("--body-file", "-F"):
            path = inline if eq else (argv[i + 1] if i + 1 < len(argv) else "-")
            text = read_stdin() if path == "-" else read_file(path)
            out += ["--body-file", "-"]
            stdin = sign(text, role, issue)
            i += 1 if eq else 2
            continue
        out.append(arg)
        i += 1
    return out, stdin


def real_gh() -> str:
    """The real `gh` on PATH, skipping this wrapper's own folder so it never calls itself."""
    path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep)
                           if Path(p).resolve() != BIN.resolve())
    return shutil.which("gh", path=path) or "gh"


def approval_in(argv: list[str]) -> str | None:
    """The approval label a command that can change labels names, if any. Comments that
    merely mention one are fine."""
    if not (tuple(argv[:2]) in {("issue", "edit"), ("pr", "edit")}
            or argv[:1] in (["api"], ["label"])):
        return None
    for label in sorted(APPROVALS):
        if any(label in arg for arg in argv):
            return label
    return None


def main(argv: list[str]) -> int:
    real = os.environ.get("OFFICE_REAL_GH") or real_gh()
    role = os.environ.get("OFFICE_AGENT_ROLE")
    stdin = None
    if role and approval_in(argv):
        print(f"`{approval_in(argv)}` is the owner's approval; agents never set it.",
              file=sys.stderr)
        return 1
    if role:
        argv, stdin = sign_args(argv, role, os.environ.get("OFFICE_ISSUE"),
                                lambda p: Path(p).read_text(), sys.stdin.read)
    if stdin is None:
        return subprocess.run([real, *argv]).returncode
    return subprocess.run([real, *argv], input=stdin, text=True).returncode


def install(bin_dir: Path = BIN) -> Path:
    """Writes the agents' commands into `bin_dir` (gitignored): the signing `gh` wrapper
    and `office-lease`. Returns the directory, which goes first on agents' PATH."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, entry in (("gh", "office.ghshim:main"), ("office-lease", "office.ports:cli")):
        module, func = entry.split(":")
        script = (f"#!{sys.executable}\n"
                  "import sys\n"
                  f"sys.path.insert(0, {str(ROOT)!r})\n"
                  f"from {module} import {func}\n"
                  f"sys.exit({func}(sys.argv[1:]))\n")
        tool = bin_dir / name
        if not tool.exists() or tool.read_text() != script:
            tool.write_text(script)
            tool.chmod(0o755)
    return bin_dir
