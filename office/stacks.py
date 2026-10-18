"""Stack guides: `docs/stack/*.md`, one per tool the office knows how to work with.

Each guide starts with a small header saying which files identify its stack:

    ---
    name: Django
    layer: Backend
    detect: manage.py, */manage.py
    ---

A `detect` pattern is a glob relative to the repo root, optionally followed by `~ text`
to require that a matching file contains that text (`docker-compose.yml ~ postgres`).
Each guide has an `## Agent guidance` section, which the office puts into every agent's prompt
on a repo where the stack is detected. Adding a stack means adding a guide; no code
changes. Detection only globs a few shallow patterns, so it is cheap to run per prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from office.config import ROOT

GUIDES = ROOT / "docs" / "stack"
HEADER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
GUIDANCE = re.compile(r"^## Agent guidance\s*$(.*?)(?=^## |\Z)", re.M | re.S)


@dataclass(frozen=True)
class Stack:
    name: str
    layer: str
    detect: tuple[str, ...]
    guidance: str
    path: Path


def parse(path: Path, text: str) -> Stack | None:
    """A guide, or None if it has no header with a `name` and `detect` patterns."""
    m = HEADER.match(text)
    if not m:
        return None
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    detect = tuple(p.strip() for p in fields.get("detect", "").split(",") if p.strip())
    if not fields.get("name") or not detect:
        return None
    g = GUIDANCE.search(text)
    return Stack(fields["name"], fields.get("layer", ""), detect,
                 g.group(1).strip() if g else "", path)


def load(guides: Path = GUIDES) -> list[Stack]:
    stacks = []
    for path in sorted(guides.glob("*.md")):
        stack = parse(path, path.read_text())
        if stack:
            stacks.append(stack)
    return stacks


def matches(root: Path, pattern: str) -> bool:
    glob, _, text = (part.strip() for part in pattern.partition("~"))
    for path in root.glob(glob):
        if not text:
            return True
        try:
            if text in path.read_text(errors="ignore"):
                return True
        except OSError:
            continue
    return False


def detect(stacks: list[Stack], root: Path) -> list[Stack]:
    """The stacks with a pattern that matches the repo."""
    return [s for s in stacks if any(matches(root, p) for p in s.detect)]


def prompt_section(found: list[Stack]) -> str:
    """The agent guidance of every detected stack, for the prompts."""
    if not found:
        return ("No stack guide matches this repo, so follow its own `AGENTS.md` and the "
                "conventions already in the code.")
    parts = []
    for s in found:
        rel = s.path.relative_to(ROOT) if s.path.is_relative_to(ROOT) else s.path
        parts.append(f"### {s.name} ({s.layer}, from the office's `{rel}`)\n\n"
                     f"{s.guidance or '(no agent guidance yet)'}")
    return "\n\n".join(parts)
