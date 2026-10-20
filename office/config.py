"""Local office configuration, saved to .office/config.json (gitignored).

The target repos are remembered here so a restart doesn't ask again. Everything else is
an optional override of the defaults below. One office process can run several repos,
owned by the same person and sharing the machine's subscriptions, so some settings are
machine-wide and the rest can be overridden per repo under `repos`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / ".office" / "config.json"
WORKSPACE = ROOT / "workspace"

# Settings that describe the machine and its subscriptions, not one repo, so `repos`
# can't override them: every repo's agents count against the same limits and ports.
MACHINE_WIDE = {"repo", "start_repos", "repos", "limits", "poll_seconds", "idle_poll_seconds",
                "rate_limit_pause_minutes", "agent_ports", "ports_per_agent", "reserved_ports"}
# Dict settings whose overrides merge onto the defaults instead of replacing them.
MERGED = ("limits", "codex_sandbox")


@dataclass
class Config:
    # The repo single-repo commands (plan, stop, release...) use when given none.
    repo: str | None = None
    # The repos `office start` runs, in one process, when given none.
    start_repos: list[str] = field(default_factory=list)
    # Per-repo overrides of any setting not in MACHINE_WIDE, keyed by owner/name, such as
    # {"owner/name": {"database_url": "postgres://...", "fixed_ports": {...}}}.
    repos: dict[str, dict] = field(default_factory=dict)
    # How many agents of each role may run at once, across every repo the office runs:
    # they share one Claude and one ChatGPT subscription.
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
    # Ports. Each engineer, reviewer and tester run leases a block of ports_per_agent
    # ports from agent_ports, skipping busy ports and the owner's reserved ranges.
    agent_ports: str = "40000-44999"
    ports_per_agent: int = 10
    reserved_ports: list[str] = field(
        default_factory=lambda: ["3000-3099", "5173-5199", "8000-8099"]
    )
    # Named port sets that must match configuration outside the repo, such as
    # {"oauth": [3011, 3012]} for a sign-in provider's allowed origins. One issue at a
    # time claims a set with `office-lease <name>`.
    fixed_ports: dict[str, list[int]] = field(default_factory=dict)
    # The target's local Postgres, as postgres://user:password@host:port/dbname, for
    # dropping agents' throwaway databases. Unset, it's read from the compose file.
    database_url: str | None = None
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
        for name in MERGED:
            merged = getattr(cls(), name)
            merged.update(data.get(name, {}))
            setattr(cfg, name, merged)
        for repo in cfg.repos:
            cfg.for_repo(repo)  # fail at startup on a bad override, not mid-run
        return cfg

    def for_repo(self, repo: str) -> Config:
        """The settings for one repo: these, with its `repos` overrides applied."""
        overrides = self.repos.get(repo, {})
        fields = self.__dataclass_fields__
        bad = sorted(k for k in overrides if k in MACHINE_WIDE or k not in fields)
        if bad:
            raise ValueError(f"`repos.{repo}` in .office/config.json can't set "
                             f"{', '.join(bad)}: unknown, or a machine-wide setting")
        changes = {k: ({**getattr(self, k), **v} if k in MERGED else v)
                   for k, v in overrides.items()}
        return replace(self, **changes)

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")
