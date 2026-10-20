# AGENTS.md

Guidance for every coding agent working on this repo. Codex reads this file directly. Claude Code reads it through `CLAUDE.md`, which imports it.

## Current state

Early. The orchestrator, the five roles, `office check` and `office start` are built and unit tested. The full loop has run end to end on a sandbox repo, but not on a production project yet. The project's goal is in the README: one person running a business with the output of a whole product and development team. `README.md` is the overview and the index of every doc. `docs/HOW-IT-WORKS.md` explains the agent loop and the delivery workflow, and each other doc in `docs/` has one scope (see the README's Documentation table).

## Commands

```bash
uv sync                                  # install
make verify                              # ruff + pytest + docs check: the definition of done
uv run pytest tests/test_planner.py      # one test file
uv run pytest -k blocker                 # tests matching a name
uv run office check owner/name           # readiness check (read-only)
uv run office start owner/name --dry-run # print the plan, change nothing
uv run office docs serve owner/name      # browse a target's docs site
uv run office plan owner/name            # what happens next (read-only)
uv run office stop owner/name [--now]    # drain (or stop immediately) a running office
uv run playwright install chromium       # once, for office shoot and its tests
```

Never run `office start` without `--dry-run` against a repo the owner hasn't asked you to work on: it files issues, pushes branches and merges PRs.

## Code map

- `office/planner.py` is pure logic (labels → next task) and has no I/O. Keep it that way, and test changes to it in `tests/test_planner.py`.
- `office/orchestrator.py` applies verdicts. Its tests (`tests/test_orchestrator.py`) use a fake GitHub and stubbed agents; extend the fakes rather than calling real CLIs in tests.
- Role prompts live in `office/prompts/`, with `{{name}}` placeholders that are filled in a single pass. Every prompt ends with the shared `_verdict.md`. When you add an outcome, update the prompt, the `allowed` set in the orchestrator and a test together.
- All external commands go through `office/shell.run`, which strips API keys from the environment. Git calls on a target go through `Workspace.git`, which serializes them and retries lock contention.
- Everything the office posts to GitHub is signed (`office/signature.py`): the orchestrator in `office/gh.py`, agents through the `gh` wrapper in `office/ghshim.py`. The signature's marker must never start with `<!-- office:`, because the planner treats those comments as state.
- `office/ports.py` leases ports to agent runs. Leases are local files that only live as long as a run; never make them outlive it.
- `office/stacks.py` reads `docs/stack/*.md`, detects which guides match a target and builds the prompts' stack section. It holds no stack knowledge itself; keep that in the guides.
- `office/databases.py` drops agents' throwaway databases in the target's compose Postgres. It only ever touches names starting with `office_`; keep that guard.
- `office/shoot.py` (Playwright) has a real-browser test in `tests/test_shoot.py`. Run `uv run playwright install chromium` once first.

## What this project is

A Python orchestrator that runs an agent swarm on a **target** GitHub repo. That repo is a separate project, cloned into a local `workspace/` that this repo doesn't track. The swarm acts as a product development office with five roles: PM, Designer, Engineer, Reviewer and Tester. It loops until every open issue is done or waiting on a human. This repo is the office. Don't confuse its code with the target repo's code.

## Invariants to keep when building it

These come from `docs/WORKFLOW.md`, `docs/TESTING.md` and `docs/ARCHITECTURE.md`, and are hard requirements. Read those for the full reasoning.

- **GitHub Issues is the only state.** Issues, labels, comments and PRs on the target repo hold all task state. The orchestrator keeps no hidden state beyond which agents it is currently running, and it touches GitHub only through `office/gh.py`.
- **Agents do the work; the orchestrator moves the cards.** Agents end with a JSON verdict. Only the orchestrator changes status labels, files blockers, files follow-up issues and merges.
- **Labels form a state machine.** The flow is `status:triage` → `status:design` (optional) → `status:ready` → `status:in-progress` → `status:in-review` → `status:testing` → `status:done`. Anything waiting on a human is labelled `blocked:human` (a repo's own `blocked` label counts too), and agents skip it. An open issue with no status label is treated as triage. A rejected review or a failed test sends the issue back to `status:ready`. To claim an issue, an agent assigns it and adds `status:in-progress`. Stale claims must expire.
- **Each role runs on a fixed CLI and subscription:**
  - PM, Designer and Engineers run on `claude` (Claude Code, headless `-p`) with a Claude subscription.
  - Reviewers and Testers run on `codex` with a ChatGPT subscription.
  - API keys are never used. The orchestrator unsets `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` in each agent's environment and refuses to start if a CLI reports API-key auth.
  - When a role hits its usage limit, that role pauses. It never falls back to API billing.
- **Code is written by one model and checked by another.** Claude writes the code; Codex reviews and tests it.
- **Merging and deploying are treated differently.**
  - The Tester merges a PR only after the target repo's full verification gate passes locally and the acceptance criteria are verified. CI must also pass if the repo has it.
  - Deploying and releasing are always a human decision. A merge never triggers either.
- **Blockers follow a fixed template.** Every blocker has the sections Decision needed, Context, Options, Recommendation and Blocks, and is labelled `office:blocker` plus `blocked:human`. Three failures in a row on one issue also file a blocker.
- **Startup has a fixed sequence:**
  1. Ask for the target repo (`owner/name`), or read it from a CLI argument or saved config.
  2. Check `gh`, `claude` and `codex` auth.
  3. Clone the target repo.
  4. Create any missing labels.
  5. If the impeccable skill isn't committed, file the "Add the impeccable design skill" issue (`status:ready`, `priority:p0`). An engineer adds it in a reviewed PR, and design waits until that issue closes.
  6. Start the loop.
- **Stop condition:** the office idles and posts a summary of open blockers when no issue can be acted on.
- **Engineers work in isolation.** Each one gets its own git worktree of the target repo.
- **The office cleans up after agents.** Anything an agent leaves running in its worktree or on its leased ports is stopped, and every database it created under its issue's `office_` prefix is dropped after the run, even a failed one. The office never drops a database outside that prefix.
- **Agents only use leased ports.** Each engineer, reviewer and tester run gets its own block from `agent_ports`, never one in `reserved_ports` or already in use. Fixed sets that must match outside configuration are claimed with `office-lease`, one issue at a time.
- **The docs site is part of every delivery.** The target's MkDocs site and its user manual at `docs/manual/` are updated in the same PR as each user-visible change, screenshots come from `office shoot`, and `mkdocs build --strict` must pass. `office start` serves the site live from the main clone.
- **Sequencing isn't a human decision.** "Wait for #N" is a `waiting` verdict with `depends_on`, not a blocker. Human requests that conflict with documented scope are blocked, not closed.
- **Design uses impeccable.** The Designer runs impeccable's `shape` command and produces markdown only (a design doc plus an implementation prompt), never images or Figma files. Engineers use impeccable for UI work, and the tester runs its `detect` command on UI changes.
- **Stopping never loses work.** The first Ctrl-C or `office stop` drains: nothing new starts and running agents finish. Only a second Ctrl-C or `--now` ends agents, and those runs never count as failures. Only one office runs per repo.
- **The orchestrator runs locally** as a long-running process, not on a server or in GitHub Actions.

## Target repos

The stacks the office supports are listed in `docs/stack/README.md`, one guide per tool (Django, Next.js, Nuxt, Vite, Tailwind, Postgres, Hetzner and Traefik, and Vercel). Whatever the stack, it expects target repos to have:

- an `AGENTS.md` (with a `CLAUDE.md` that imports it) and `docs/`, which every agent reads first
- a single `make verify` or `npm run verify` command as the definition of done
- the design system kept in the repo, with the impeccable skill committed

Role prompts should build on these conventions instead of re-describing them.

**Stack-specific knowledge lives only in `docs/stack/`.** Role prompts, `office/` code and the other docs stay stack-neutral. When the office learns something that applies to every repo on one stack (a command that must run first, a test-isolation rule, a deploy pattern), add it to that stack's guide: under `## Agent guidance` if agents must follow it, which puts it in their prompts, otherwise under `## Setting up a repo`. A new stack is a new guide with a `detect` header; `tests/test_stacks.py` checks every guide is valid and listed in `docs/stack/README.md`.

## Office context vs target context

Two contexts are maintained separately, and neither leaks into the other:

| | Office context | Target context |
|---|---|---|
| What | How the office works: roles, labels, verdicts, prompts, config | How the product works and how to work in it |
| Where | This repo: `README.md`, `AGENTS.md`, `docs/`, `office/prompts/` | The target repo: its `AGENTS.md`, `docs/`, `PRODUCT.md`, `DESIGN.md` |
| Maintained by | Changes to this repo, under the drift rules below | The office's agents, in the same PR as the change (`office/prompts/_context.md`) |
| Local state | `.office/config.json` | `workspace/<owner>__<repo>/`, its worktrees and docs log (`office clean` removes them) |

- **Nothing target-specific goes into this repo:** no repo names, domains, quirks or findings from a target. Use `example.com` and `owner/name` placeholders. Something learned about a target belongs in the target repo, as a fix in a PR or a practice issue.
- **Nothing office-specific goes into a target's files.** Agents may mention the office in issue and PR comments, but a target's code and docs must make sense to a team that has never heard of the office. `_context.md` tells every agent this.
- **Keep suggesting better practices for the target.** The PM's recurring practices review (`office/prompts/pm_practices.md`) and every agent's verdict can file `Practice:` issues. When you change what the office checks, update the review prompt and `office/readiness.py` together.

## Preventing documentation drift

The docs are the product until the code exists, and afterwards they are what the office's own agents read. Keep them true.

- **Docs change in the same commit as the behavior.** If a change alters a role, label, workflow step, command, invariant or decision, update every doc that describes it in that same commit. A commit that makes a doc wrong is incomplete.
- **Small files, one scope each, all linked.** Each doc covers one topic, stated in its first paragraph and in the README's Documentation table. When a doc grows a second topic, split it into its own file rather than adding a section. Every doc is linked from the README, and every doc links back to it.
- **One home per fact.** Each fact lives in the doc that owns its scope, and other docs link to it instead of restating it:

  | Doc | Owns |
  |---|---|
  | `README.md` | The goal, status, quick start, target stack summary, core principles, and the index |
  | `docs/HOW-IT-WORKS.md` | The agent loop and the delivery workflow, as diagrams |
  | `docs/USAGE.md` | Commands, configuration, stop and resume, day-to-day use, switching projects |
  | `docs/WORKFLOW.md` | Roles, the flow, blockers, dependencies, practice suggestions, the stop condition |
  | `docs/LABELS.md` | Every label: meaning, color, who sets and removes it, repo labels honored. Kept in sync with `office/labels.py` by a test. |
  | `docs/TESTING.md` | How changes are verified, UI and UX testing, and testing the office |
  | `docs/DOCS-SITE.md` | The target's MkDocs site and user manual |
  | `docs/ARCHITECTURE.md` | Modules, claims, cleanup, billing rules, context separation |
  | `docs/DECISIONS.md` | Decisions and inspiration |
  | `docs/SETUP.md` | The office machine, and the conventions every target follows whatever its stack |
  | `docs/stack/*.md` | Everything specific to one stack: its setup, its agent rules, its deployment. `docs/stack/README.md` owns the guide format and the reference combination. |
  | `docs/INTEGRATION.md` | Onboarding an existing repo |

  When two docs disagree, fix the one that isn't the owner.
- **This file mirrors the invariants.** When an invariant changes in its owning doc (labels, role-to-CLI mapping, merge and deploy rules, startup sequence, stop condition), update the invariants section above in the same commit. If a change alters the loop or the delivery workflow, update the diagrams in `docs/HOW-IT-WORKS.md` too.
- **Agent guidance lives here only.** `CLAUDE.md` contains nothing but the import of this file. Put new guidance here, never in `CLAUDE.md`.
- **Every markdown file is linked from the README's Documentation table.** Add a row when you add a doc and remove it when you delete one. Files a *target* repo is expected to have (such as `DESIGN.md`) are mentioned as plain text, not linked.
- **Label what isn't built.** Describe anything not yet implemented as **(planned)**. When it ships, remove the marker and replace any example output with real output. Never document a command, flag or file that doesn't exist without that marker.
- **Commands must be real.** Every command in the docs must either have been run or be marked planned. When the code adds or renames a command, update this file, `docs/USAGE.md` and the guides together.
- **Run the check before committing:** `./scripts/check-docs.sh`. It fails if a markdown file isn't linked from the README or a relative link points at a missing file.

## Other rules

- Read every file before publishing or pushing it. This repo is public.
- Never add names, IPs, domains or other details from the private reference repos. Use `example.com` and `owner/name` placeholders.
