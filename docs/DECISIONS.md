# Decisions

The decisions that shape the office, and the projects it borrows from. Read these before changing anything that looks like a deliberate tradeoff.

- **Language:** Python. The orchestrator shells out to `gh`, `claude` and `codex`.
- **Runs on:** a local machine, as a long-running process. No server and no GitHub Actions.
- **Merging:** agents merge PRs themselves, but only after the change has been fully tested locally: the full test suite passes and the Codex tester has verified the acceptance criteria. CI must also pass when the target repo has CI.
- **Releasing:** always the owner's decision, made by adding an approval label to the one open release issue. The office does the rest: it lists what's waiting, checks the default branch hasn't moved since, runs verify and the target's own `make release`, has Codex check the live site, and only rolls back on a second approval. Agents never release, and the office never rolls back on its own, because a rollback across a schema change can do as much harm as a bad release.
- **Several repos, one office:** one process runs every repo the owner wants worked on, because they all draw on the same two subscriptions. Machine-wide limits and pauses keep three repos from running three times the agents, and from hitting the usage limit three times as fast. Each repo keeps its own GitHub state, clone and settings, so the repos never see each other's work.
- **Design deliverables:** prompts and design documents (markdown) only. No Figma, no image mockups.
- **Delivery includes docs:** every target repo has an MkDocs site with a user manual and feature catalog, kept current in every PR and served live while the office runs.
- **UI testing:** [Playwright](https://playwright.dev/) screenshots and objective UX checks, posted on PRs.
- **Design tool:** the [impeccable](https://github.com/pbakaus/impeccable) skill, committed to each target repo. The Designer uses `shape` to plan, engineers use it for UI work, and the tester runs its `detect` command on changed UI files. When a target doesn't have it, `office start` files a p0 setup issue for an engineer rather than committing it directly, so the change is reviewed and tested like any other and the orchestrator never writes to the target.
- **Identity:** the office uses the owner's own `gh` login rather than a bot account, so setup needs nothing extra. Everything it posts is signed with the role that wrote it, so its comments can be told apart from the owner's. Label changes still show the owner's account.
- **Resources are leased by the harness, not managed by an agent:** databases and ports go to each agent run by name or by lease, reach it in its environment, and are cleaned up when the run ends. That's deterministic bookkeeping, which a project or engineering manager agent would only make slower, costlier and less reliable.
- **Stack knowledge lives in stack guides:** one markdown guide per tool in `docs/stack/`, detected per target and pasted into agents' prompts. The office's code and prompts stay stack-neutral, so anyone can add support for their stack by contributing a guide, with no code change.

## Inspiration

Similar projects this design borrows from:

- **[MetaGPT](https://github.com/FoundationAgents/MetaGPT):** role-based software company (PM, architect, engineer) following standard operating procedures. It inspired the role split and handoff artifacts.
- **[ChatDev](https://github.com/OpenBMB/ChatDev):** a virtual software company of communicating agents (CEO, CTO, programmer, tester).
- **[OpenAI Symphony](https://medium.com/@ritukampani/openai-open-sources-symphony-the-specification-that-wants-to-coordinate-your-ai-coding-army-97b6d78633fc):** a spec for coordinating coding agents through an issue tracker. It inspired making GitHub Issues the control plane.
- **[Claude Code agent teams](https://addyosmani.com/blog/claude-code-agent-teams/):** a lead agent delegating to parallel teammates.
- **[Agent Swarm](https://feedbagel.com/post/agent-swarm-multi-agent-orchestration-framework-for-ai-coding-assistants):** a lead agent that takes tasks from GitHub or Slack and delegates to Claude Code, Codex and Gemini workers.
- **Codex plugin for Claude Code:** Codex as a review gate on Claude's work. It inspired the cross-model review rule.


---
[← Back to the README](../README.md)
