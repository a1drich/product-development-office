# Architecture

How the office is built: its modules, how they fit together, the rules it enforces on models and billing, and how it keeps its own context apart from the target repo's.

## Modules

| Module | Responsibility |
|---|---|
| `office/cli.py` | The `office` command: `check`, `labels`, `start`, `plan`, `shoot`, `docs`, `clean` |
| `office/auth.py` | Startup checks: no API keys, and `gh`, `claude` and `codex` logged in with subscriptions |
| `office/readiness.py` | `office check`: the integration checklist as code |
| `office/planner.py` | Pure logic: from labels, priorities and claims, which task each issue needs next |
| `office/orchestrator.py` | The loop. Runs tasks on a thread pool within per-role limits, then applies each verdict: labels, comments, blockers, follow-up issues, merges. |
| `office/agents.py` | Runs `claude -p` or `codex exec` in the right folder and parses the JSON verdict |
| `office/prompts/` | One prompt per role, plus the shared verdict format |
| `office/gh.py` | Thin adapter over `gh`. The orchestrator touches GitHub only through it. |
| `office/workspace.py` | The main clone, plus one git worktree per issue on branch `office/issue-N`. Git calls are serialized and retried on lock contention, because worktrees share refs. |
| `office/shoot.py` | `office shoot`: Playwright screenshots and UX checks |
| `office/docs_server.py` | Keeps the target's MkDocs site served and current while the office runs |
| `office/plan.py` | `office plan`: a read-only view of what happens next |
| `office/clean.py` | `office clean`: removes a project's local state and, optionally, the office's traces on GitHub |
| `office/config.py` | Settings and their defaults; overrides live in `.office/config.json` |

## How it fits together

- **Agents do the work; the office moves the cards.** Agents edit issue bodies, write code, open PRs and post review and test reports. Each one ends with a JSON verdict, such as `ready`, `opened`, `approve`, `changes`, `pass`, `fail` or `blocked`. Only the orchestrator changes status labels, files blockers and merges, so the state machine never depends on an agent remembering to update a label.
- **Claims.** Before an engineer starts, the office assigns the issue, sets `status:in-progress` and posts a claim comment. At startup, every leftover claim is released. While running, a claim older than `claim_ttl_minutes` (two hours by default) with no agent running is also released back to `status:ready`.
- **Verification** (review, testing, conflicts, CI and merging) is described in [Testing](TESTING.md).
- **Reviews are PR comments.** The office runs under your GitHub account, which can't approve its own PRs. The reviewer posts its findings as a PR comment, and its verdict decides whether the issue moves on.
- **Stopping.** Every command the office runs, agents included, gets its own process group, so a terminal Ctrl-C reaches only the office. It decides what to do: the first Ctrl-C (SIGINT) drains, and a second one or SIGTERM ends every tracked command group and exits. The office writes `workspace/<owner>__<repo>.pid` while it runs, which `office stop` signals and a second `office start` refuses to override.
- **Cleanup.** When an agent finishes in an issue's worktree, the office stops anything it left running there, such as a dev server. The shared main clone is never cleaned, because other agents may be working in it.
- **Dependencies.** An agent that can't continue until another issue lands returns `waiting` with the issue numbers. That isn't a human decision, so the office parks the issue with `office:waiting` and requeues it when those issues close.
- **Usage limits.** When an agent reports a usage limit, its role pauses for `rate_limit_pause_minutes` and the other roles keep working.

## Model and billing rules

These rules are hard requirements, and `office start` enforces them:

| Role | Allowed tool | Auth |
|---|---|---|
| PM, Designer, Engineers | `claude` (Claude Code CLI, headless `-p` mode) | Claude subscription login only |
| Reviewers | `codex` (Codex CLI, `codex exec`) | ChatGPT subscription login only |
| Testers | `codex` (Codex CLI) | ChatGPT subscription login only |

- Startup refuses to run if `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `ANTHROPIC_AUTH_TOKEN` is set, or if `claude auth status` or `codex login status` reports anything other than a subscription login. Those variables are also stripped from every agent's environment.
- Subscriptions have rate limits. When an agent hits a usage limit, the orchestrator pauses that role and keeps the others running. It does not fall back to API billing.

## Two contexts, kept separate

The office's own context (roles, labels, prompts) lives in this repo. The target's context (its `AGENTS.md`, `docs/`, `PRODUCT.md`, `DESIGN.md`) lives in the target. Agents keep the target's context current in the same PR as each change, and never write about the office into the target's files, so the target repo still makes sense to a human team without the office. See [AGENTS.md](../AGENTS.md#office-context-vs-target-context).


---
[← Back to the README](../README.md)
