# Product Development Office

An autonomous agent swarm that works like an outsourced product development office. Point it at a GitHub repository and a team of AI agents (a product manager, a designer, engineers, reviewers and testers) plans, builds, reviews and tests the product. It keeps going until every remaining piece of work is waiting on a human decision.

> **Status:** early. The orchestrator, all five roles, `office check` and `office start` are built and unit tested. Each agent CLI has been smoke-tested on its own, but the full loop has not yet run end to end on a live repo, so watch the first runs closely.

## Target stack

The office is optimized for repos built on this stack:

- **Backend:** [Django](https://www.djangoproject.com/) + [Django REST Framework](https://www.django-rest-framework.org/), managed with [uv](https://docs.astral.sh/uv/), linted with [ruff](https://docs.astral.sh/ruff/)
- **Frontends:** [TypeScript](https://www.typescriptlang.org/) web apps ([Nuxt](https://nuxt.com/) or [Next.js](https://nextjs.org/)) with [Tailwind CSS](https://tailwindcss.com/)
- **Data:** [Postgres](https://www.postgresql.org/) (and [Redis](https://redis.io/) where needed) via [Docker Compose](https://docs.docker.com/compose/)
- **Local dev:** external services mocked, demo data from a `seed_demo` command
- **Deployment:** [Docker](https://www.docker.com/) containers on [Hetzner](https://www.hetzner.com/cloud/), behind [Traefik](https://doc.traefik.io/traefik/)

It expects these repo conventions:

- `AGENTS.md` (imported by `CLAUDE.md`) and `docs/` describe the product, and every agent reads them first.
- A single verification command (`make verify` or `npm run verify`) is the definition of done.
- The design system lives in the repo (`DESIGN.md` or `docs/design-system.md`), and the [impeccable](https://github.com/pbakaus/impeccable) design skill is committed to it.
- Releases and deploys are always a human decision. Agents never run them.

## Documentation

| Doc | What it covers |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Installing the office, preparing a target repo, deploying to Hetzner behind Traefik |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | Step-by-step checklist for onboarding an existing repo |
| [AGENTS.md](AGENTS.md) | Guidance for any coding agent working on this repo, including how to keep the docs from drifting |
| [CLAUDE.md](CLAUDE.md) | Imports `AGENTS.md` for Claude Code |
| [LICENSE](LICENSE) | MIT |

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
| **Designer** | Claude Code (Claude subscription) + [impeccable](https://github.com/pbakaus/impeccable) | Uses impeccable's `shape` command to turn product issues into markdown design documents (flows, screens, states, copy, tokens and components) with an implementation prompt for engineers, and posts them on the issue before engineering starts. |
| **Engineer** (1..n) | Claude Code (Claude subscription) | Picks up `ready` issues, works in an isolated git worktree, implements the change (using impeccable for any UI work), runs the verify command and opens a PR linked to the issue. |
| **Reviewer** | Codex CLI (ChatGPT/Codex subscription) | Reviews every PR for correctness, security and maintainability. It either approves or requests changes, and changes go back to an engineer. |
| **Tester** | Codex CLI (ChatGPT/Codex subscription) | Checks out approved PRs locally and verifies them against the acceptance criteria: merges in the base branch, runs the full verify command, writes missing tests, exercises the change and runs the impeccable detector on UI changes. If it passes, the office merges the PR; otherwise it goes back to an engineer, and any bugs found are filed as issues. |

## Getting started

```bash
git clone https://github.com/a1drich/product-development-office && cd product-development-office
uv sync

uv run office check owner/name               # is the repo ready? (read-only)
uv run office check owner/name --file-issues # file an issue for each gap
uv run office start owner/name --dry-run     # show what the office would do
uv run office start owner/name               # run until blocked
```

Run with no repo, `office start` asks for one and remembers it in `.office/config.json`:

```
$ uv run office start
? Which GitHub repo should the office work on? (owner/name) acme/widget-app
✓ no API keys: none set
✓ gh: logged in
✓ claude: logged in (max)
✓ codex: logged in (ChatGPT)
✓ cloned acme/widget-app into workspace/widget-app
✓ labels ready (14 created)
→ verify command: make verify
12:00:01 starting triage on #12 (pm)
```

Startup steps:

1. Read the target repo (`owner/name`) from the argument or the saved config, or ask for it.
2. Check that no API key is set, and that `gh`, `claude` (subscription login) and `codex` (ChatGPT login) are logged in. Startup refuses to continue otherwise.
3. Clone the repo into `workspace/`, which this project's git history doesn't track.
4. Create any missing office labels on the target repo.
5. Hand control to the orchestrator loop. Stop it with Ctrl-C.

| Command | What it does |
|---|---|
| `office check [repo] [--run-verify] [--file-issues]` | Checks a repo against the [integration checklist](docs/INTEGRATION.md). `--run-verify` also runs its verify command on a fresh clone. `--file-issues` files one `status:triage` issue per gap, so fixing readiness becomes the office's first work. |
| `office labels [repo]` | Creates the office labels |
| `office start [repo] [--dry-run] [--exit-when-idle]` | Runs the office. `--dry-run` prints the plan and changes nothing. `--exit-when-idle` exits instead of polling once everything is blocked or done. |

Settings such as concurrency per role, poll intervals and the claim timeout can be overridden in `.office/config.json`. The defaults are in `office/config.py`.

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12+ for you)
- [GitHub CLI](https://cli.github.com/) (`gh`), logged in with access to the target repo
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code), logged in with a Claude subscription
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
| `blocked:human` | Waiting for a human decision. Agents skip it until the label is removed. A repo's existing `blocked` label is treated the same way. |
| `office:blocker` | A decision issue the office filed. Also carries `blocked:human` until answered. |
| `office:status` | The single "Office status" issue, where the office lists everything waiting on a human |
| `priority:p0`..`p3` | Set by the PM; p0 is worked first. A repo's existing `P0`..`P3` labels count too. |

An open issue with no status label is treated as `status:triage`, so issues filed by humans are picked up automatically.

### Blockers

Anything that needs human input becomes a blocker. Examples are product direction, ambiguous requirements, credentials or access, spending money, legal or brand questions, and irreversible actions such as deploying or releasing. Merging a fully tested PR is *not* a blocker.

An agent never files a blocker itself. It returns the decision, context, options and recommendation in its verdict, and the office files a GitHub issue labelled `office:blocker` and `blocked:human` from this template, so every blocker can be answered in under a minute:

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

The blocked issue also gets `blocked:human` and a comment linking the blocker. To answer, comment on the blocker with your decision and remove its `blocked:human` label. On the next cycle the PM reads the answer and updates the issues listed under "Blocks". The office then unblocks them and closes the blocker.

If an agent fails on the same issue three times in a row, for example by crashing, timing out or returning no verdict, the office files a blocker for it instead of retrying forever.

### Stop condition

Each cycle, the orchestrator checks whether any issue can still be acted on. When every open issue is blocked or done and no agent is running, the office goes idle. It writes the list of everything waiting on a human into the "Office status" issue (office decisions first, then by priority), then polls every 10 minutes for answers. With `--exit-when-idle`, it exits instead.

## Model and billing rules

These rules are hard requirements, and `office start` enforces them:

| Role | Allowed tool | Auth |
|---|---|---|
| PM, Designer, Engineers | `claude` (Claude Code CLI, headless `-p` mode) | Claude subscription login only |
| Reviewers | `codex` (Codex CLI, `codex exec`) | ChatGPT subscription login only |
| Testers | `codex` (Codex CLI) | ChatGPT subscription login only |

- Startup refuses to run if `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `ANTHROPIC_AUTH_TOKEN` is set, or if `claude auth status` or `codex login status` reports anything other than a subscription login. Those variables are also stripped from every agent's environment.
- Subscriptions have rate limits. When an agent hits a usage limit, the orchestrator pauses that role and keeps the others running. It does not fall back to API billing.

## Architecture

| Module | Responsibility |
|---|---|
| `office/cli.py` | The `office` command: `check`, `labels`, `start` |
| `office/auth.py` | Startup checks: no API keys, and `gh`, `claude` and `codex` logged in with subscriptions |
| `office/readiness.py` | `office check`: the integration checklist as code |
| `office/planner.py` | Pure logic: from labels, priorities and claims, which task each issue needs next |
| `office/orchestrator.py` | The loop. Runs tasks on a thread pool within per-role limits, then applies each verdict: labels, comments, blockers, follow-up issues, merges. |
| `office/agents.py` | Runs `claude -p` or `codex exec` in the right folder and parses the JSON verdict |
| `office/prompts/` | One prompt per role, plus the shared verdict format |
| `office/gh.py` | Thin adapter over `gh`. The orchestrator touches GitHub only through it. |
| `office/workspace.py` | The main clone, plus one git worktree per issue on branch `office/issue-N` |

How it fits together:

- **Agents do the work; the office moves the cards.** Agents edit issue bodies, write code, open PRs and post review and test reports. Each one ends with a JSON verdict, such as `ready`, `opened`, `approve`, `changes`, `pass`, `fail` or `blocked`. Only the orchestrator changes status labels, files blockers and merges, so the state machine never depends on an agent remembering to update a label.
- **Claims.** Before an engineer starts, the office assigns the issue, sets `status:in-progress` and posts a claim comment. A claim older than `claim_ttl_minutes` (two hours by default) with no agent running is released back to `status:ready`. That covers crashed or stopped runs.
- **Reviews are PR comments.** The office runs under your GitHub account, which can't approve its own PRs. The reviewer posts its findings as a PR comment, and its verdict decides whether the issue moves on.
- **Merging.** After a `pass` verdict, the office waits up to 30 minutes for the PR's CI checks, then squash-merges and deletes the branch. If CI fails, the issue goes back to an engineer.
- **Usage limits.** When an agent reports a usage limit, its role pauses for `rate_limit_pause_minutes` and the other roles keep working.

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
- **Design tool:** the [impeccable](https://github.com/pbakaus/impeccable) skill, committed to each target repo. The Designer uses `shape` to plan, engineers use it for UI work, and the tester runs its `detect` command on changed UI files.

## License

[MIT](LICENSE)
