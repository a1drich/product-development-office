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
| `office/ports.py` | Port leases: a block of ports per agent run, named fixed sets claimed with `office-lease`, and stopping servers left on them |
| `office/signature.py` | The signature on everything the office posts to GitHub |
| `office/ghshim.py` | The `gh` wrapper on every agent's `PATH` that signs what the agent posts |
| `office/stacks.py` | Reads the [stack guides](stack/README.md), detects which apply to a target, and builds the stack section of every prompt |
| `office/databases.py` | Finds the target's Postgres from its compose file, and drops the throwaway databases agents create |
| `office/clean.py` | `office clean`: removes a project's local state and, optionally, the office's traces on GitHub |
| `office/config.py` | Settings and their defaults; overrides live in `.office/config.json` |

## How it fits together

- **Agents do the work; the office moves the cards.** Agents edit issue bodies, write code, open PRs and post review and test reports. Each one ends with a JSON verdict, such as `ready`, `opened`, `approve`, `changes`, `pass`, `fail` or `blocked`. Only the orchestrator changes status labels, files blockers and merges, so the state machine never depends on an agent remembering to update a label.
- **Claims.** Before an engineer starts, the office assigns the issue, sets `status:in-progress` and posts a claim comment. At startup, every leftover claim is released. While running, a claim older than `claim_ttl_minutes` (two hours by default) with no agent running is also released back to `status:ready`.
- **Verification** (review, testing, conflicts, CI and merging) is described in [Testing](TESTING.md).
- **Signed posts.** The office acts through your own `gh` login, so GitHub shows its comments as yours. Everything it posts ends with a line naming who wrote it, such as `🤖 Tester (Codex) · product development office`, plus a hidden `<!-- office-agent role=tester issue=59 -->` marker. The orchestrator signs its own comments and issues as "Office" in `office/gh.py`. Agents post with `gh` themselves, so the office puts a `gh` wrapper first on each agent's `PATH` (with `OFFICE_AGENT_ROLE`, `OFFICE_ISSUE` and the real `gh` in `OFFICE_REAL_GH`). It signs the body of `issue comment`, `pr comment`, `pr create`, `pr review` and `issue create`, and passes everything else through. Edits aren't signed, so an issue body the PM rewrites doesn't collect signatures. Label changes can't carry a signature, so they still show your account. The marker doesn't start with `<!-- office:`, which is reserved for the orchestrator's state marks.
- **Reviews are PR comments.** The office runs under your GitHub account, which can't approve its own PRs. The reviewer posts its findings as a PR comment, and its verdict decides whether the issue moves on.
- **Stopping.** Every command the office runs, agents included, gets its own process group, so a terminal Ctrl-C reaches only the office. It decides what to do: the first Ctrl-C (SIGINT) drains, and a second one or SIGTERM ends every tracked command group and exits. The office writes `workspace/<owner>__<repo>.pid` while it runs, which `office stop` signals and a second `office start` refuses to override.
- **Cleanup.** When an agent finishes in an issue's worktree, the office stops anything it left running there, such as a dev server. The shared main clone is never cleaned, because other agents may be working in it.
- **Ports.** Every engineer, reviewer and tester run leases its own block of ports (`ports_per_agent`, 10 by default) from `agent_ports`. The office skips any block that overlaps the owner's `reserved_ports` or has something listening on it, so agents never collide with each other or with the owner's own dev servers. The block reaches the agent in its prompt and in `OFFICE_PORTS` and `OFFICE_PORT_BASE`. Ports that must match configuration outside the repo, such as a sign-in provider's allowed origins, are named sets in `fixed_ports`. An agent claims one only when it needs it, with `office-lease <name>`, which gives it to one issue at a time and refuses if anything outside the office is listening on it. When the run ends, even a failed one, the office stops anything listening on the run's ports and releases them. Leases are files in `workspace/<owner>__<repo>-leases/`, so `office plan` can show them, and `office start` clears them. Steps in the main clone (triage, design, blocker answers) get no ports.
- **Stack guides.** Each role prompt includes a "This repo's stack" section: the `## Agent guidance` of every [stack guide](stack/README.md) whose `detect` patterns match the target's main clone, checked each time a prompt is built. The office's code and prompts hold no stack knowledge of their own.
- **Databases.** Each issue owns a database name prefix, `office_<repo hash>_i<N>_`, which agents get in their prompt and in `OFFICE_DB_PREFIX`. They name every database they create with it, through the target's own overrides (such as a test-database name or database URL variable). After every engineer, reviewer or tester run, even a failed one, the office drops every database with that prefix. Only one agent works on an issue at a time, and the repo hash keeps two targets on one Postgres server apart, so a prefix never belongs to another run. `office start` also sweeps up any of this repo's `office_` databases left by a crash, and `office clean` drops them all. This is the [Postgres](stack/POSTGRES.md) guide's cleanup: the office finds Postgres through the target's compose file (the service running a `postgres` image, its published port and credentials), connects from the host, and never drops a name outside `office_`. The `database_url` setting in `.office/config.json` overrides the compose file when the target's Postgres is somewhere else. A target with neither gets no database cleanup.
- **Releases.** The orchestrator runs releases itself, never an agent, and only on an approval label (see [Releases](WORKFLOW.md#releases)). It finds who added the label from the issue's events and accepts it only from a repo admin. Because the office uses your own `gh` login, a label an agent added would also show your account, so the agents' `gh` wrapper refuses any `issue edit`, `pr edit`, `api` or `label` command that names an approval label. The release issue's comments record each deploy and rollback with its commit (`<!-- office:deployed <sha> -->`), and its body records the commit its list was written at, so the state stays on GitHub. Verify and the release command run in a fresh worktree pinned to the approved commit, with leased ports and the issue's database prefix like an agent run, and the rollback command gets the last closed release's commit as `REF`. With no earlier release on record, the office refuses to roll back rather than run the command without one.
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
