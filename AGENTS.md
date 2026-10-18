# AGENTS.md

Guidance for every coding agent working on this repo. Codex reads this file directly. Claude Code reads it through `CLAUDE.md`, which imports it.

## Current state

Design stage. `README.md` is the spec. `docs/SETUP.md` covers setting up the office machine, the conventions target repos are expected to follow, and the Hetzner + Traefik deployment pattern. `docs/INTEGRATION.md` is the checklist for onboarding an existing repo.

There is no code, build, lint or test setup yet. Add those commands here once they exist. Don't assume any. The only command today is `./scripts/check-docs.sh`.

## What this project is

A Python orchestrator that runs an agent swarm on a **target** GitHub repo. That repo is a separate project, cloned into a local `workspace/` that this repo doesn't track. The swarm acts as a product development office with five roles: PM, Designer, Engineer, Reviewer and Tester. It loops until every open issue is done or waiting on a human. This repo is the office. Don't confuse its code with the target repo's code.

## Invariants to keep when building it

These come from the README and are hard requirements. Read the README for the full reasoning.

- **GitHub Issues is the only state.** Issues, labels, comments and PRs on the target repo hold all task state. The orchestrator keeps no hidden state of its own. Agents act on GitHub only through a thin adapter over `gh`.
- **Labels form a state machine.** The flow is `status:triage` → `status:design` (optional) → `status:ready` → `status:in-progress` → `status:in-review` → `status:testing` → `status:done`. Anything waiting on a human is labelled `blocked:human`, and agents skip it. A rejected review or a failed test sends the issue back to `status:ready`. To claim an issue, an agent assigns it and adds `status:in-progress`. Stale claims must expire.
- **Each role runs on a fixed CLI and subscription:**
  - PM, Designer and Engineers run on `claude` (Claude Code, headless `-p`) with a Claude subscription.
  - Reviewers and Testers run on `codex` with a ChatGPT subscription.
  - API keys are never used. The orchestrator unsets `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` in each agent's environment and refuses to start if a CLI reports API-key auth.
  - When a role hits its usage limit, that role pauses. It never falls back to API billing.
- **Code is written by one model and checked by another.** Claude writes the code; Codex reviews and tests it.
- **Merging and deploying are treated differently.**
  - The Tester merges a PR only after the target repo's full verification gate passes locally and the acceptance criteria are verified. CI must also pass if the repo has it.
  - Deploying and releasing are always a human decision. A merge never triggers either.
- **Blockers follow a fixed template.** Every blocker has the sections Decision needed, Context, Options, Recommendation and Blocks.
- **Startup has a fixed sequence:**
  1. Ask for the target repo (`owner/name`), or read it from a CLI argument or saved config.
  2. Check `gh`, `claude` and `codex` auth.
  3. Clone the target repo.
  4. Create any missing labels.
  5. Start the loop.
- **Stop condition:** the office idles and posts a summary of open blockers when no issue can be acted on.
- **Engineers work in isolation.** Each one gets its own git worktree of the target repo.
- **The Designer produces markdown only:** design documents and prompts, never images or Figma files.
- **The orchestrator runs locally** as a long-running process, not on a server or in GitHub Actions.

## Target repos

The office is optimized for target repos that use Django, DRF and `uv`/`ruff` for the backend, TypeScript frontends (Nuxt or Next.js), Postgres via `docker compose`, and Docker deploys on Hetzner behind Traefik. It expects those repos to have:

- an `AGENTS.md` (with a `CLAUDE.md` that imports it) and `docs/`, which every agent reads first
- a single `make verify` or `npm run verify` command as the definition of done
- the design system kept in the repo

Role prompts should build on these conventions instead of re-describing them.

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
