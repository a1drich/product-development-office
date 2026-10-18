"""Keeps the target repo's MkDocs site running and current while the office runs.

`mkdocs serve` runs from the main clone, which the office resets to the default branch
after every merge, and MkDocs live-reloads on file changes, so the site always shows the
latest manual and screenshots.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from office.shell import clean_env

log = logging.getLogger("office")

MKDOCS = ["uvx", "--with", "mkdocs-material", "mkdocs"]


class DocsServer:
    def __init__(self, clone: Path, port: int):
        self.clone = clone
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.log_path = clone.parent / f"{clone.name}-mkdocs.log"

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def available(self) -> bool:
        return (self.clone / "mkdocs.yml").exists()

    def ensure(self) -> None:
        """Starts the server if the repo has a site and it isn't running."""
        if not self.available or (self.proc and self.proc.poll() is None):
            return
        if self.proc is not None:
            log.warning("docs server exited (%s); restarting", self.proc.returncode)
        logfile = self.log_path.open("a")
        self.proc = subprocess.Popen(
            [*MKDOCS, "serve", "--livereload", "-a", f"127.0.0.1:{self.port}"],
            cwd=self.clone,
            stdout=logfile,
            stderr=subprocess.STDOUT,
            env=clean_env(),
        )
        log.info("docs site: %s (log: %s)", self.url, self.log_path)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
