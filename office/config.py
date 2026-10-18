"""Local office configuration, saved to .office/config.json (gitignored).

The target repo is remembered here so a restart doesn't ask again. Everything else is
an optional override of the defaults below.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / ".office" / "config.json"
WORKSPACE = ROOT / "workspace"


@dataclass
class Config:
    repo: str | None = None
    # How many agents of each role may run at once.
    limits: dict[str, int] = field(
        default_factory=lambda: {"pm": 1, "designer": 1, "engineer": 1, "reviewer": 1, "tester": 1}
    )
    poll_seconds: int = 60
    idle_poll_seconds: int = 600
    # An in-progress claim older than this, with no local agent running it, is released.
    claim_ttl_minutes: int = 120
    # How long a role pauses after hitting its subscription usage limit.
    rate_limit_pause_minutes: int = 30
    agent_timeout_minutes: int = 60
    # The PM reviews the repo's practices at most this often, while fewer than
    # max_open_practices practice issues are open.
    practices_interval_hours: int = 24
    max_open_practices: int = 3
    # Practice suggestions wait for a human to approve them (remove blocked:human)
    # before the office works on them.
    practices_need_approval: bool = True
    # Claude Code permission mode for headless agents ("auto", "acceptEdits", ...).
    claude_permission_mode: str = "auto"
    # Where the target repo's MkDocs site is served while the office runs.
    docs_port: int = 8787
    # Codex sandbox per role. Testers run Docker and dev servers, so they need full access.
    codex_sandbox: dict[str, str] = field(
        default_factory=lambda: {"reviewer": "workspace-write", "tester": "danger-full-access"}
    )

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> Config:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        cfg = cls(**known)
        # Merge partial dict overrides onto the defaults.
        for name in ("limits", "codex_sandbox"):
            merged = getattr(cls(), name)
            merged.update(data.get(name, {}))
            setattr(cfg, name, merged)
        return cfg

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")
