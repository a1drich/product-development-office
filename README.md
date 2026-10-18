# Product Development Office

An autonomous agent swarm that works like an outsourced product development office. Point it at a GitHub repository and a team of AI agents (a product manager, a designer, engineers, reviewers and testers) plans, builds, reviews and tests the product. It keeps going until every remaining piece of work is waiting on a human decision.

## Goal

**Let one person run a business with the output of a whole product and development team.** The owner does what only an owner can: sets direction, makes product and business decisions, approves suggestions and reviews the product through its user manual. The office does everything else: planning, design, engineering, code review, testing, documentation and keeping the repo healthy. Every design choice here serves that: work runs without supervision, anything that needs the owner arrives as a short decision that can be answered in under a minute, and the docs site shows what was built without reading code.

> **Status:** early. The orchestrator, all five roles, `office check` and `office start` are built and unit tested, and the full loop has run end to end on a sandbox repo: triage, design, implementation, cross-model review, screenshot testing, merges, blockers, dependencies and practice suggestions. It hasn't run on a production project yet, so watch the first runs closely.

## How it works

```
 you open an issue ─▶ PM triages ─▶ Designer designs ─▶ Engineer builds ─▶ Codex reviews ─▶ Codex tests ─▶ office merges
                                    (manual entry)      (code, tests,                       (Playwright        │
                                                         user manual)                         screenshots)      ▼
                   you review the user manual and screenshots on the live MkDocs site ◀─────────────────────────┘
```

The office runs a loop on your machine. It reads the target repo's GitHub issues, works out what each one needs next, hands that work to an agent and applies the agent's verdict. It keeps going until everything left is waiting on you. **[How it works](docs/HOW-IT-WORKS.md)** explains the agent loop and the delivery workflow (MkDocs, Playwright screenshots, the user manual) with diagrams.

## Quick start

```bash
git clone https://github.com/a1drich/product-development-office && cd product-development-office
uv sync && uv run playwright install chromium

uv run office check owner/name     # is the repo ready? (read-only)
uv run office start owner/name     # run until everything is waiting on you
uv run office plan owner/name      # in another terminal: what happens next
```

Then ask for features by opening issues on the target repo. See [Usage](docs/USAGE.md) for everything else.

## Target stack

The office is optimized for repos built on this stack:

- **Backend:** [Django](https://www.djangoproject.com/) + [Django REST Framework](https://www.django-rest-framework.org/), managed with [uv](https://docs.astral.sh/uv/), linted with [ruff](https://docs.astral.sh/ruff/)
- **Frontends:** [TypeScript](https://www.typescriptlang.org/) web apps ([Nuxt](https://nuxt.com/) or [Next.js](https://nextjs.org/)) with [Tailwind CSS](https://tailwindcss.com/)
- **Data:** [Postgres](https://www.postgresql.org/) (and [Redis](https://redis.io/) where needed) via [Docker Compose](https://docs.docker.com/compose/)
- **Local dev:** external services mocked, demo data from a `seed_demo` command
- **Deployment:** [Docker](https://www.docker.com/) containers on [Hetzner](https://www.hetzner.com/cloud/), behind [Traefik](https://doc.traefik.io/traefik/)

It expects these repo conventions (details in the [setup guide](docs/SETUP.md#2-preparing-a-target-repo)):

- `AGENTS.md` (imported by `CLAUDE.md`) and `docs/` describe the product, and every agent reads them first.
- A single verification command (`make verify` or `npm run verify`) is the definition of done.
- The design system lives in the repo (`DESIGN.md` or `docs/design-system.md`), and the [impeccable](https://github.com/pbakaus/impeccable) design skill is committed to it.
- An [MkDocs](https://www.mkdocs.org/) site over `docs/`, with a user manual and feature catalog at `docs/manual/` (see [Docs site and user manual](docs/DOCS-SITE.md)).
- Releases and deploys are always a human decision. Agents never run them.

## Core principles

1. **GitHub Issues is the only source of truth.** Every task, decision, handoff and status change lives in an issue, a label, a comment or a PR on the target repo. Agents keep no hidden state, so a human can see and steer everything from GitHub.
2. **Run until blocked.** The office loops on its own. It stops only when every open issue is either done or waiting on a human.
3. **Humans decide, agents execute.** When an agent needs a product, business, access or taste decision it can't make, it files a **blocker** issue and moves on to other work. It does not guess.
4. **Subscriptions only, no API keys.** Every agent runs on a logged-in CLI subscription (Claude or ChatGPT/Codex). API keys are never used. See [Architecture](docs/ARCHITECTURE.md#model-and-billing-rules).
5. **Different models write and check the code.** Code written by Claude is reviewed and tested by Codex, so a model's blind spots don't approve themselves.

## Documentation

Each document has one scope. Start with **How it works**.

| Doc | Scope |
|---|---|
| [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) | The agent loop and the delivery workflow, with diagrams |
| [docs/USAGE.md](docs/USAGE.md) | Installing and running the office, building a feature, steering work, switching projects |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | The team, the flow, blockers, dependencies, practice suggestions, the stop condition |
| [docs/LABELS.md](docs/LABELS.md) | Every GitHub label the office uses: meaning, who sets and removes it, and repo labels it honors |
| [docs/TESTING.md](docs/TESTING.md) | How every change is verified (review, tests, UI and UX screenshots, CI) and how to test the office itself |
| [docs/DOCS-SITE.md](docs/DOCS-SITE.md) | The MkDocs site and user manual every target repo delivers |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Modules, how they fit together, model and billing rules, context separation |
| [docs/DECISIONS.md](docs/DECISIONS.md) | The decisions behind the design, and the projects it borrows from |
| [docs/SETUP.md](docs/SETUP.md) | The office machine, target-repo conventions, deploying to Hetzner behind Traefik |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | A step-by-step checklist for onboarding an existing repo |
| [AGENTS.md](AGENTS.md) | Guidance for coding agents working on this repo, including the documentation rules |
| [CLAUDE.md](CLAUDE.md) | Imports `AGENTS.md` for Claude Code |
| [LICENSE](LICENSE) | MIT |

## License

[MIT](LICENSE)
