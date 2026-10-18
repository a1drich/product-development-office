# AGENTS.md

Guidance for every coding agent working on this repo. Codex reads this file directly. Claude Code reads it through `CLAUDE.md`, which imports it.

## Current state

Early. The orchestrator, the five roles, `office check` and `office start` are built and unit tested. Each agent CLI has been smoke-tested, but the full loop hasn't run end to end on a live repo yet. `README.md` is the spec and documents the architecture. `docs/SETUP.md` covers the office machine, target-repo conventions and the Hetzner + Traefik deployment pattern. `docs/INTEGRATION.md` is the checklist for onboarding an existing repo.

## Commands

```bash
uv sync                                  # install
make verify                              # ruff + pytest + docs check: the definition of done
uv run pytest tests/test_planner.py      # one test file
uv run pytest -k blocker                 # tests matching a name
uv run office check owner/name           # readiness check (read-only)
uv run office start owner/name --dry-run # print the plan, change nothing
```

Never run `office start` without `--dry-run` against a repo the owner hasn't asked you to work on: it files issues, pushes branches and merges PRs.

## Code map

- `office/planner.py` is pure logic (labels → next task) and has no I/O. Keep it that way, and test changes to it in `tests/test_planner.py`.
- `office/orchestrator.py` applies verdicts. Its tests (`tests/test_orchestrator.py`) use a fake GitHub and stubbed agents; extend the fakes rather than calling real CLIs in tests.
- Role prompts live in `office/prompts/`, with `{{name}}` placeholders that are filled in a single pass. Every prompt ends with the shared `_verdict.md`. When you add an outcome, update the prompt, the `allowed` set in the orchestrator and a test together.
- All external commands go through `office/shell.run`, which strips API keys from the environment.

## What this project is

A Python orchestrator that runs an agent swarm on a **target** GitHub repo. That repo is a separate project, cloned into a local `workspace/` that this repo doesn't track. The swarm acts as a product development office with five roles: PM, Designer, Engineer, Reviewer and Tester. It loops until every open issue is done or waiting on a human. This repo is the office. Don't confuse its code with the target repo's code.

## Invariants to keep when building it

These come from the README and are hard requirements. Read the README for the full reasoning.

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
  5. Start the loop.
- **Stop condition:** the office idles and posts a summary of open blockers when no issue can be acted on.
- **Engineers work in isolation.** Each one gets its own git worktree of the target repo.
- **Design uses impeccable.** The Designer runs impeccable's `shape` command and produces markdown only (a design doc plus an implementation prompt), never images or Figma files. Engineers use impeccable for UI work, and the tester runs its `detect` command on UI changes.
- **The orchestrator runs locally** as a long-running process, not on a server or in GitHub Actions.

## Target repos

The office is optimized for target repos that use Django, DRF and `uv`/`ruff` for the backend, TypeScript frontends (Nuxt or Next.js), Postgres via `docker compose`, and Docker deploys on Hetzner behind Traefik. It expects those repos to have:

- an `AGENTS.md` (with a `CLAUDE.md` that imports it) and `docs/`, which every agent reads first
- a single `make verify` or `npm run verify` command as the definition of done
- the design system kept in the repo, with the impeccable skill committed

Role prompts should build on these conventions instead of re-describing them.

## Office context vs target context

Two contexts are maintained separately, and neither leaks into the other:

| | Office context | Target context |
|---|---|---|
| What | How the office works: roles, labels, verdicts, prompts, config | How the product works and how to work in it |
| Where | This repo: `README.md`, `AGENTS.md`, `docs/`, `office/prompts/` | The target repo: its `AGENTS.md`, `docs/`, `PRODUCT.md`, `DESIGN.md` |
| Maintained by | Changes to this repo, under the drift rules below | The office's agents, in the same PR as the change (`office/prompts/_context.md`) |
| Local state | `.office/config.json` | `workspace/<repo>/` and its worktrees |

- **Nothing target-specific goes into this repo:** no repo names, domains, quirks or findings from a target. Use `example.com` and `owner/name` placeholders. Something learned about a target belongs in the target repo, as a fix in a PR or a practice issue.
- **Nothing office-specific goes into a target's files.** Agents may mention the office in issue and PR comments, but a target's code and docs must make sense to a team that has never heard of the office. `_context.md` tells every agent this.
- **Keep suggesting better practices for the target.** The PM's recurring practices review (`office/prompts/pm_practices.md`) and every agent's verdict can file `Practice:` issues. When you change what the office checks, update the review prompt and `office/readiness.py` together.

## Preventing documentation drift

The docs are the product until the code exists, and afterwards they are what the office's own agents read. Keep them true.

- **Docs change in the same commit as the behavior.** If a change alters a role, label, workflow step, command, invariant or decision, update every doc that describes it in that same commit. A commit that makes a doc wrong is incomplete.
- **One home per fact.** The README owns the design: roles, labels, workflow, blocker template, billing rules, decisions. `docs/SETUP.md` owns installation and deployment. `docs/INTEGRATION.md` owns onboarding an existing repo. Other files summarize and link to the owner instead of restating the details. When two docs disagree, fix the one that isn't the owner.
- **This file mirrors the README's invariants.** When an invariant in the README changes (labels, role-to-CLI mapping, merge and deploy rules, startup sequence, stop condition), update the invariants section above in the same commit.
- **Agent guidance lives here only.** `CLAUDE.md` contains nothing but the import of this file. Put new guidance here, never in `CLAUDE.md`.
- **Every markdown file is linked from the README's Documentation table.** Add a row when you add a doc and remove it when you delete one. Files a *target* repo is expected to have (such as `DESIGN.md`) are mentioned as plain text, not linked.
- **Label what isn't built.** Describe anything not yet implemented as **(planned)**. When it ships, remove the marker and replace any example output with real output. Never document a command, flag or file that doesn't exist without that marker.
- **Commands must be real.** Every command in the docs must either have been run or be marked planned. When the code adds or renames a command, update this file, the README and the guides together.
- **Run the check before committing:** `./scripts/check-docs.sh`. It fails if a markdown file isn't linked from the README or a relative link points at a missing file.

## Other rules

- Read every file before publishing or pushing it. This repo is public.
- Never add names, IPs, domains or other details from the private reference repos. Use `example.com` and `owner/name` placeholders.
