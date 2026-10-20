"""`office check`: is a target repo ready for the office? Mirrors docs/INTEGRATION.md."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from office import labels as L
from office import stacks

FAIL, WARN, PASS = "fail", "warn", "pass"

# `office start` files this issue when impeccable is missing (see Office.bootstrap), and
# `office check --file-issues` uses the same title, so the gap is never filed twice.
IMPECCABLE_TITLE = "Add the impeccable design skill"
IMPECCABLE_DIRS = (".claude/skills/impeccable", ".agents/skills/impeccable")


@dataclass
class Finding:
    key: str
    level: str  # pass | warn | fail
    summary: str
    fix: str = ""
    title: str = ""

    @property
    def issue_title(self) -> str:
        return self.title or f"Office readiness: {self.summary}"


def _exists(root: Path, *names: str) -> str | None:
    for n in names:
        if (root / n).exists():
            return n
    return None


def impeccable_installed(root: Path) -> str | None:
    return _exists(root, *IMPECCABLE_DIRS)


def repo_command(root: Path, name: str) -> str | None:
    """`make <name>` or `npm run <name>`, whichever the repo defines."""
    makefile = root / "Makefile"
    if makefile.exists() and re.search(rf"^{name}\s*:", makefile.read_text(), re.M):
        return f"make {name}"
    pkg = root / "package.json"
    if pkg.exists():
        try:
            if name in json.loads(pkg.read_text()).get("scripts", {}):
                return f"npm run {name}"
        except json.JSONDecodeError:
            pass
    return None


def verify_command(root: Path) -> str | None:
    return repo_command(root, "verify")


def release_command(root: Path) -> str | None:
    return repo_command(root, "release")


def rollback_command(root: Path, ref: str | None = None) -> list[str] | None:
    """The rollback command, given the commit to go back to when there is one."""
    cmd = repo_command(root, "rollback")
    if cmd is None:
        return None
    if ref is None:
        return cmd.split()
    return [*cmd.split(), f"REF={ref}"] if cmd.startswith("make") else [*cmd.split(), "--", ref]


def check_files(root: Path) -> list[Finding]:
    out: list[Finding] = []

    if (root / "AGENTS.md").exists():
        out.append(Finding("agents-md", PASS, "AGENTS.md exists"))
    elif (root / "CLAUDE.md").exists():
        out.append(Finding(
            "agents-md", WARN, "agent guidance is only in CLAUDE.md",
            "Move CLAUDE.md's content into AGENTS.md (Codex reads AGENTS.md) and make CLAUDE.md "
            "just `@AGENTS.md`.",
        ))
    else:
        out.append(Finding(
            "agents-md", FAIL, "no AGENTS.md agent brief",
            "Write AGENTS.md: how to install, run and test (including a single test), the "
            "architecture, conventions, and the rules agents must follow.",
        ))

    claude = root / "CLAUDE.md"
    if not claude.exists():
        out.append(Finding("claude-md", WARN, "no CLAUDE.md",
                           "Add a CLAUDE.md containing `@AGENTS.md` so Claude Code reads it."))
    elif "@AGENTS.md" in claude.read_text():
        out.append(Finding("claude-md", PASS, "CLAUDE.md imports AGENTS.md"))
    elif (root / "AGENTS.md").exists():
        out.append(Finding("claude-md", WARN, "CLAUDE.md and AGENTS.md are separate files",
                           "Merge CLAUDE.md into AGENTS.md and replace it with `@AGENTS.md`."))

    cmd = verify_command(root)
    if cmd:
        out.append(Finding("verify", PASS, f"verify command: `{cmd}`"))
    else:
        out.append(Finding(
            "verify", FAIL, "no single verify command",
            "Add `make verify` (or `npm run verify`) that runs lint, tests, typecheck and frontend "
            "lint and exits non-zero on any failure. It is the definition of done.",
        ))

    release = release_command(root)
    if release:
        rollback = repo_command(root, "rollback")
        out.append(Finding("release", PASS, f"release command: `{release}`"
                           + (f", rollback: `{rollback}`" if rollback else "")))
    else:
        out.append(Finding(
            "release", WARN, "no release command",
            "Add `make release` (or `npm run release`) that puts the checked-out commit live, "
            "and `make rollback REF=<commit>` that puts an earlier commit back. The office then "
            "prepares each release for your approval and runs it once you approve.",
        ))

    docs = root / "docs"
    if docs.is_dir() and any(docs.rglob("*.md")):
        out.append(Finding("docs", PASS, "docs/ exists"))
    else:
        out.append(Finding("docs", FAIL, "no docs/ folder",
                           "Add docs/ with at least a short product brief and a decision log."))

    if (root / "PRODUCT.md").exists():
        out.append(Finding("product-md", PASS, "PRODUCT.md exists"))
    else:
        out.append(Finding(
            "product-md", WARN, "no PRODUCT.md",
            "Run impeccable's `init` command to capture users, context and voice in PRODUCT.md.",
        ))

    design = _exists(root, "DESIGN.md", "docs/design-system.md")
    if design:
        out.append(Finding("design-md", PASS, f"design system: {design}"))
    else:
        out.append(Finding(
            "design-md", WARN, "no DESIGN.md design system",
            "Run impeccable's `document` command to generate DESIGN.md from the existing code.",
        ))

    imp = impeccable_installed(root)
    if imp:
        out.append(Finding("impeccable", PASS, f"impeccable installed ({imp})"))
    else:
        out.append(Finding(
            "impeccable", FAIL, "impeccable design skill not installed",
            "Run `npx skills add pbakaus/impeccable` in the repo and commit the result, so the "
            "Designer and engineers share the same design skill. `office start` files this as "
            "its first task.",
            title=IMPECCABLE_TITLE,
        ))

    if (root / "mkdocs.yml").exists():
        out.append(Finding("mkdocs", PASS, "MkDocs site (mkdocs.yml)"))
    else:
        out.append(Finding(
            "mkdocs", WARN, "no MkDocs docs site",
            "Add mkdocs.yml (Material theme) over docs/, with the user manual in the nav, and "
            "make `uvx --with mkdocs-material mkdocs build --strict` part of the verify command.",
        ))

    if (root / "docs" / "manual" / "README.md").exists():
        out.append(Finding("manual", PASS, "user manual: docs/manual/README.md"))
    else:
        out.append(Finding(
            "manual", WARN, "no user manual / feature catalog",
            "Add docs/manual/README.md: one section per feature or page (what it's for, how to "
            "use it, desktop and mobile screenshots from docs/manual/screenshots/).",
        ))

    makefile = root / "Makefile"
    if makefile.exists() and re.search(r"^screenshots\s*:", makefile.read_text(), re.M):
        out.append(Finding("screenshots", PASS, "screenshot command: `make screenshots`"))
    else:
        out.append(Finding(
            "screenshots", WARN, "no `make screenshots` command",
            "Add a `make screenshots` target that seeds each manual page's state and captures it "
            "at desktop and mobile widths. Without one, testers fall back to `office shoot`, "
            "which can only open plain URLs.",
        ))

    if (root / "docs" / "manual" / "pages.json").exists():
        out.append(Finding("pages", PASS, "screenshot pages: docs/manual/pages.json"))
    else:
        out.append(Finding(
            "pages", WARN, "no docs/manual/pages.json",
            'List the pages to screenshot: {"pages": [{"name": "home", "path": "/", '
            '"expect": "visible text"}]}. `office shoot` captures them.',
        ))

    if (root / ".env.example").exists():
        out.append(Finding("env-example", PASS, ".env.example exists"))
    else:
        out.append(Finding("env-example", WARN, "no .env.example",
                           "Add a .env.example that works as-is for local development."))

    found = stacks.detect(stacks.load(), root)
    if found:
        out.append(Finding("stack", PASS, "stack guides: " + ", ".join(s.name for s in found)))
    else:
        # Not a gap in the repo, so it never becomes an issue: the office lacks a guide.
        out.append(Finding("stack", PASS, "no stack guide matches; agents follow AGENTS.md "
                                          "alone (add one in the office's docs/stack/)"))

    workflows = root / ".github" / "workflows"
    if workflows.is_dir() and any(workflows.glob("*.y*ml")):
        out.append(Finding("ci", PASS, "CI workflows exist"))
    else:
        out.append(Finding("ci", WARN, "no CI workflow",
                           "Add a workflow that runs the verify command's checks on PRs."))
    return out


def check_github(repo_info: dict, label_names: set[str]) -> list[Finding]:
    out: list[Finding] = []
    if repo_info.get("hasIssuesEnabled"):
        out.append(Finding("issues", PASS, "GitHub Issues enabled"))
    else:
        out.append(Finding("issues", FAIL, "GitHub Issues disabled",
                           "gh repo edit owner/name --enable-issues"))
    missing = [lb.name for lb in L.LABELS if lb.name not in label_names]
    if missing:
        out.append(Finding("labels", WARN, f"{len(missing)} office labels missing",
                           "`office labels owner/name` creates them; `office start` does too."))
    else:
        out.append(Finding("labels", PASS, "office labels exist"))
    return out


def worst(findings: list[Finding]) -> str:
    levels = {f.level for f in findings}
    return FAIL if FAIL in levels else WARN if WARN in levels else PASS
