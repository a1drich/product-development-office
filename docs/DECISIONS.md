# Decisions

The decisions that shape the office, and the projects it borrows from. Read these before changing anything that looks like a deliberate tradeoff.

- **Language:** Python. The orchestrator shells out to `gh`, `claude` and `codex`.
- **Runs on:** a local machine, as a long-running process. No server and no GitHub Actions.
- **Merging:** agents merge PRs themselves, but only after the change has been fully tested locally: the full test suite passes and the Codex tester has verified the acceptance criteria. CI must also pass when the target repo has CI.
- **Design deliverables:** prompts and design documents (markdown) only. No Figma, no image mockups.
- **Delivery includes docs:** every target repo has an MkDocs site with a user manual and feature catalog, kept current in every PR and served live while the office runs.
- **UI testing:** [Playwright](https://playwright.dev/) screenshots and objective UX checks, posted on PRs.
- **Design tool:** the [impeccable](https://github.com/pbakaus/impeccable) skill, committed to each target repo. The Designer uses `shape` to plan, engineers use it for UI work, and the tester runs its `detect` command on changed UI files.

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
