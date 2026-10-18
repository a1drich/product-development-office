# Product Development Office

An autonomous agent swarm that works like an outsourced product development office. Point it at a GitHub repository and a team of AI agents (a product manager, a designer, engineers, reviewers and testers) plans, builds, reviews and tests the product. It keeps going until every remaining piece of work is waiting on a human decision.

> **Status:** design stage. This README describes the intended system. Nothing is implemented yet.

## Target stack

The office is optimized for repos built on this stack:

- **Backend:** [Django](https://www.djangoproject.com/) + [Django REST Framework](https://www.django-rest-framework.org/), managed with [uv](https://docs.astral.sh/uv/), linted with [ruff](https://docs.astral.sh/ruff/)
- **Frontends:** [TypeScript](https://www.typescriptlang.org/) web apps ([Nuxt](https://nuxt.com/) or [Next.js](https://nextjs.org/)) with [Tailwind CSS](https://tailwindcss.com/)
- **Data:** [Postgres](https://www.postgresql.org/) (and [Redis](https://redis.io/) where needed) via [Docker Compose](https://docs.docker.com/compose/)
- **Local dev:** external services mocked, demo data from a `seed_demo` command
- **Deployment:** [Docker](https://www.docker.com/) containers on [Hetzner](https://www.hetzner.com/cloud/), behind [Traefik](https://doc.traefik.io/traefik/)

It expects these repo conventions:

- `CLAUDE.md`, `AGENTS.md` and `docs/` describe the product, and every agent reads them first.
- A single verification command (`make verify` or `npm run verify`) is the definition of done.
- The design system lives in the repo (`DESIGN.md` or `docs/design-system.md`).
- Releases and deploys are always a human decision. Agents never run them.

See the **[setup guide](docs/SETUP.md)** for installing the office, preparing a target repo and deploying to Hetzner behind Traefik.

## Core principles

1. **GitHub Issues is the only source of truth.** Every task, decision, handoff and status change lives in an issue, a label, a comment or a PR on the target repo. Agents keep no hidden state, so a human can see and steer everything from GitHub.
2. **Run until blocked.** The office loops on its own. It stops only when every open issue is either done or waiting on a human.
3. **Humans decide, agents execute.** When an agent needs a product, business, access or taste decision it can't make, it files a **blocker** issue and moves on to other work. It does not guess.
4. **Subscriptions only, no API keys.** Every agent runs on a logged-in CLI subscription (Claude or ChatGPT/Codex). API keys are never used. See [Model and billing rules](#model-and-billing-rules).
5. **Different models write and check the code.** Code written by Claude is reviewed and tested by Codex, so a model's blind spots don't approve themselves.

## The team

| Role | Runs on | Responsibilities |
|---|---|---|
| **Product Manager** | Claude Code (Claude subscription) | Reads the repo and its open issues, writes and keeps the backlog, breaks epics into scoped issues with acceptance criteria, sets priorities, files blockers for human decisions, and decides when an issue is done. |
| **Designer** | Claude Code (Claude subscription) | Turns product issues into markdown design documents (UX flows, UI specs, component guidance) and implementation prompts for engineers. Posts them on the issue or commits them to the repo before engineering starts. |
| **Engineer** (1..n) | Claude Code (Claude subscription) | Picks up `ready` issues, works in an isolated git worktree or branch, implements the change, and opens a PR linked to the issue. |
| **Reviewer** | Codex CLI (ChatGPT/Codex subscription) | Reviews every PR for correctness, security and maintainability. It either approves or requests changes, and changes go back to an engineer. |
| **Tester** | Codex CLI (ChatGPT/Codex subscription) | Checks out approved PRs locally and verifies them against the acceptance criteria: runs the full test suite, writes missing tests and exercises the change. It merges the PR when everything passes, or sends it back or files bug issues. |

## Getting started (planned)

On a fresh, empty checkout, the office first asks **which GitHub repository to work on**:

```
$ ./office start
? Which GitHub repo should the office work on? (owner/name) acme/widget-app
✓ gh authenticated as <you>
✓ claude logged in (subscription)
✓ codex logged in (ChatGPT subscription)
✓ Cloned acme/widget-app into ./workspace/widget-app
✓ Created office labels on acme/widget-app
→ PM is reading the repo and the backlog...
```

Bootstrap steps:

1. Prompt for the target repo (`owner/name`). It can also come from a CLI argument or a saved config so later restarts skip the question.
2. Check that the prerequisites are logged in: `gh auth status`, `claude` (subscription login) and `codex` (ChatGPT login).
3. Clone the repo into a local workspace that this project's git history doesn't track.
4. Create the label set on the target repo (see below) if it's missing.
5. Hand control to the orchestrator loop.

### Prerequisites

- [GitHub CLI](https://cli.github.com/) (`gh`), logged in with access to the target repo
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code), logged in with a Claude Pro/Max subscription
- [Codex CLI](https://github.com/openai/codex), logged in with a ChatGPT subscription

## How work flows

Issue labels drive the workflow. The orchestrator polls the target repo, finds issues in each state and dispatches them to the matching role.

```
            ┌────────────────────────────── blocked:human ◀── any agent, at any step
            │                                    │ (human answers, removes label)
            ▼                                    ▼
 status:triage ─PM─▶ status:design ─Designer─▶ status:ready ─Engineer─▶ status:in-review
                         (optional)                 ▲                         │ Reviewer (Codex)
                                                    │ changes requested       ▼
                                                    └──────────────── status:testing
                                                    ▲ bug filed               │ Tester (Codex)
                                                    └─────────────────────────▼
                                                                         status:done ─PM─▶ closed
```

### Labels

| Label | Meaning |
|---|---|
| `status:triage` | New or unscoped. The PM needs to write acceptance criteria and a priority. |
| `status:design` | Needs UX/UI work before engineering. |
| `status:ready` | Fully specified; an engineer can pick it up. |
| `status:in-progress` | An engineer is working on it (the issue is assigned to that agent). |
| `status:in-review` | A PR is open and waiting for Codex review. |
| `status:testing` | The PR is approved and waiting for Codex testing. |
| `status:done` | Verified locally and merged by the tester. |
| `blocked:human` | Waiting for a human decision. Agents skip it until the label is removed. |
| `role:*` | Optional hint for which role owns the issue. |
| `priority:p0`..`p3` | Set by the PM. |

### Blockers

Anything that needs human input becomes a blocker. Examples are product direction, ambiguous requirements, credentials or access, spending money, legal or brand questions, and irreversible actions such as deploying or releasing. Merging a fully tested PR is *not* a blocker.

A blocker is a GitHub issue labelled `blocked:human`. It is written so a human can answer it in under a minute:

```markdown
## Decision needed
Should guest checkout be supported in v1?

## Context
Issue #42 asks for a checkout flow. Supporting guests changes the data model (#43) and the auth work (#44).

## Options
1. **Guest checkout allowed** – faster conversion, ~2 extra issues of work
2. **Account required** – simpler, matches current auth

## Recommendation
Option 2 for v1. Revisit after launch.

## Blocks
#42, #43, #44
```

Blocked issues reference the blocker. When a human comments and removes `blocked:human`, the PM reads the answer, updates the affected issues and the loop picks them up again.

### Stop condition

Each cycle, the orchestrator checks whether any issue can still be acted on. The office **stops** (or idles and polls at a low frequency) when every open issue is `blocked:human` or `status:done`. It then posts a summary listing the open blockers so the human knows exactly what to decide.

## Model and billing rules

These rules are hard requirements, and the orchestrator should enforce them at startup:

| Role | Allowed tool | Auth |
|---|---|---|
| PM, Designer, Engineers | `claude` (Claude Code CLI, headless `-p` mode) | Claude subscription login only |
| Reviewers | `codex` (Codex CLI, `exec` / review mode) | ChatGPT subscription login only |
| Testers | `codex` (Codex CLI) | ChatGPT subscription login only |

- Do not set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. The orchestrator should unset them in each agent's environment and refuse to start if a CLI reports API-key auth.
- Subscriptions have rate limits. When an agent hits a usage limit, the orchestrator pauses that role and keeps the others running. It does not fall back to API billing.

## Architecture (planned)

- **Orchestrator.** A long-running Python process on the local machine that polls GitHub, applies the label state machine, enforces concurrency limits (for example, N engineers in parallel) and spawns role agents as CLI subprocesses.
- **Role prompts.** One system prompt or instruction file per role (PM, Designer, Engineer, Reviewer, Tester). Each one defines the role's responsibilities, the GitHub actions it may take and the blocker rules.
- **Workspaces.** Each engineer works in its own git worktree or branch of the target repo, so parallel work never collides.
- **GitHub adapter.** A thin wrapper over `gh` for reading and writing issues, labels, comments and PRs. Agents act on GitHub only through this adapter, so every action is visible there.
- **Locking.** An agent claims an issue by assigning it and adding `status:in-progress`. Stale claims expire, so a crashed agent doesn't hold an issue forever.

## Inspiration

Similar projects this design borrows from:

- **[MetaGPT](https://github.com/FoundationAgents/MetaGPT):** role-based software company (PM, architect, engineer) following standard operating procedures. It inspired the role split and handoff artifacts.
- **[ChatDev](https://github.com/OpenBMB/ChatDev):** a virtual software company of communicating agents (CEO, CTO, programmer, tester).
- **[OpenAI Symphony](https://medium.com/@ritukampani/openai-open-sources-symphony-the-specification-that-wants-to-coordinate-your-ai-coding-army-97b6d78633fc):** a spec for coordinating coding agents through an issue tracker. It inspired making GitHub Issues the control plane.
- **[Claude Code agent teams](https://addyosmani.com/blog/claude-code-agent-teams/):** a lead agent delegating to parallel teammates.
- **[Agent Swarm](https://feedbagel.com/post/agent-swarm-multi-agent-orchestration-framework-for-ai-coding-assistants):** a lead agent that takes tasks from GitHub or Slack and delegates to Claude Code, Codex and Gemini workers.
- **Codex plugin for Claude Code:** Codex as a review gate on Claude's work. It inspired the cross-model review rule.

## Decisions

- **Language:** Python. The orchestrator shells out to `gh`, `claude` and `codex`.
- **Runs on:** a local machine, as a long-running process. No server and no GitHub Actions.
- **Merging:** agents merge PRs themselves, but only after the change has been fully tested locally: the full test suite passes and the Codex tester has verified the acceptance criteria. CI must also pass when the target repo has CI.
- **Design deliverables:** prompts and design documents (markdown) only. No Figma, no image mockups.

## License

[MIT](LICENSE)
