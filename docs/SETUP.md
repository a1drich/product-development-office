# Setup guide

This guide covers two things:

1. [Setting up the machine that runs the office](#1-the-office-machine)
2. [Preparing a target repo](#2-preparing-a-target-repo) so the agents can work on it

Everything specific to one stack (Django, Next.js, Postgres, deploying to Hetzner behind Traefik and so on) is in the [stack guides](stack/README.md).

---

## 1. The office machine

The office runs as a long-running process on a local machine.

### Install

| Tool | Why |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Runs the orchestrator, and installs Python 3.12+ for it |
| [GitHub CLI](https://cli.github.com/) (`gh`) | All issue, label and PR work |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | PM, Designer and Engineers |
| [Codex CLI](https://github.com/openai/codex) | Reviewers and Testers |
| [Docker](https://docs.docker.com/get-docker/) | Each target repo's local services, such as its database |
| [Node.js](https://nodejs.org/) 24 + npm | Target repo frontends |

### Log in, with subscriptions only

```bash
gh auth login                                  # needs write access to the target repo
gh auth refresh -h github.com -s workflow      # only if agents should edit .github/workflows/

claude                                         # then /login with a Claude subscription
codex login                                    # choose "Sign in with ChatGPT"
```

Make sure no API keys are set in your shell. The office refuses to start if one is set:

```bash
unset ANTHROPIC_API_KEY OPENAI_API_KEY ANTHROPIC_AUTH_TOKEN
```

### Install and start

```bash
git clone https://github.com/a1drich/product-development-office
cd product-development-office
uv sync
uv run playwright install chromium           # once, for UI screenshots

uv run office check acme/widget-app          # is the repo ready?
uv run office start acme/widget-app --dry-run
uv run office start acme/widget-app          # or just `office start` to be asked
```

For an existing repo, work through the [integration guide](INTEGRATION.md) first.

---

## 2. Preparing a target repo

The agents work best on a repo that follows the conventions below, plus those in the [stack guide](stack/README.md) for each tool it uses. A repo that already looks like this needs no extra setup.

- **One verify command.** `make verify` (or `npm run verify`) runs every check and is the definition of done. Engineers run it before opening a PR, and testers run it again on the PR branch before merging. It must pass on a fresh clone, with no `.env` or installed dependencies, because that's where the office verifies a release: have it create a missing `.env` from `.env.example` and install missing dependencies from the lockfiles first, without rewriting them (`npm ci`, not `npm install`).
- **Release and rollback commands (optional).** `make release` (or `npm run release`) puts the checked-out commit live (the office runs it in a checkout of the commit you approved), and `make rollback REF=<commit>` (or `npm run rollback -- <commit>`) puts an earlier commit back. With them, the office prepares each release for your approval and runs it once you approve (see [Releases](WORKFLOW.md#releases)). Each stack guide's deploying section says what they run. `AGENTS.md` states the production URL, so the tester can check the live site after a release.

### Docs site and user manual

`docs/` is an [MkDocs](https://www.mkdocs.org/) site (`mkdocs.yml`, Material theme), and it is delivered with every change:

- `docs/manual/README.md` is the user manual and feature catalog: one section per feature or page, with desktop and mobile screenshots from `docs/manual/screenshots/`. The owner reviews the product through it.
- `docs/manual/pages.json` lists the pages to screenshot. `make screenshots` captures them, with each page's state set up. `office shoot` is the fallback for repos without that command.
- `uvx --with mkdocs-material mkdocs build --strict` must pass. Add it to `make verify` so broken links and pages missing from the nav fail the build.
- While the office runs, the site is served live at `http://127.0.0.1:8787` from the target's main clone, and refreshed after every merge. `office docs serve owner/name` serves it on its own.

The [integration guide](INTEGRATION.md#add-the-docs-site-and-user-manual) has starter files.

### Files the agents read

| File | Purpose |
|---|---|
| `AGENTS.md` | Commands, architecture, conventions and rules, such as when to file a blocker and what never to touch. Every agent reads it first. |
| `CLAUDE.md` | Just `@AGENTS.md`, so Claude Code reads the same file as Codex |
| `mkdocs.yml`, `docs/manual/` | The docs site and user manual. Every role keeps it current. |
| `PRODUCT.md`, `DESIGN.md` or `docs/design-system.md` | Who the users are and the visual system. The Designer works from and updates these. |
| `docs/` | Strategy, specs, data model, decision log. Agents follow decisions written here instead of "fixing" them. |
| `docs/BACKLOG.md` (optional) | An index of what's done, what agents can build now and what's blocked |
| `docs/OWNER-TODO.md` (optional) | Things only a human can do (accounts, money, legal, DNS) |

### Local development must work offline

- **Mock every external service** behind an env flag (for example `META_MOCK=true`, `BILLING_MOCK=true`), so the full product runs end to end with no third-party accounts or internet.
- **Tests use their own database**, separate from the dev database. This lets parallel agents run test suites without clobbering each other.

### GitHub

- Turn on Issues. The office creates its labels on first run.
- Commit the [impeccable](https://github.com/pbakaus/impeccable) design skill (`npx skills add pbakaus/impeccable`), so every agent's fresh clone has it. If you don't, `office start` files it as the office's first task.
- Add CI (`.github/workflows/ci.yml`) that runs the same checks as `make verify` on pull requests. The tester waits for it before merging.
- Protect `main` from force-pushes. Agents merge PRs, but only through `gh pr merge`.

---
[← Back to the README](../README.md)
