# Workflow

Who does what, and how an issue moves from request to merge. The orchestrator polls the target repo, finds issues in each state and dispatches them to the matching role. For how a PR is verified, see [Testing](TESTING.md).

## The team

| Role | Runs on | Responsibilities |
|---|---|---|
| **Product Manager** | Claude Code (Claude subscription) | Reads the repo and its open issues, writes and keeps the backlog, breaks epics into scoped issues with acceptance criteria, sets priorities, files blockers for human decisions, and decides when an issue is done. |
| **Designer** | Claude Code (Claude subscription) + [impeccable](https://github.com/pbakaus/impeccable) | Uses impeccable's `shape` command to turn product issues into markdown design documents (flows, screens, states, copy, tokens and components). Each one includes the user-manual entry, the screens to capture and an implementation prompt for engineers, and is posted on the issue before engineering starts. |
| **Engineer** (1..n) | Claude Code (Claude subscription) | Picks up `ready` issues, works in an isolated git worktree, implements the change (using impeccable for any UI work), runs the verify command and opens a PR linked to the issue. |
| **Reviewer** | Codex CLI (ChatGPT/Codex subscription) | Reviews every PR for correctness, security and maintainability. It either approves or requests changes, and changes go back to an engineer. |
| **Tester** | Codex CLI (ChatGPT/Codex subscription) | Checks out approved PRs locally and verifies them against the acceptance criteria: merges in the base branch, runs the full verify command, writes missing tests, exercises the change, screenshots and UX-checks every page with [Playwright](https://playwright.dev/) (`office shoot`), checks the user manual and runs the impeccable detector on UI changes. If it passes, the office merges the PR; otherwise it goes back to an engineer, and any bugs found are filed as issues. |

## The flow

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

## Follow-up issues

Any agent can ask for follow-up issues in its verdict: bugs it found, work it split off, or practice suggestions. The office files them with `status:triage`. To avoid duplicates, every agent's prompt lists the open issues, and agents point at an existing issue (or comment on it) instead of filing a new one. As a backstop, the office skips a follow-up whose title matches an open issue's, ignoring case, punctuation, articles and a `Practice:` prefix.

## Labels

Labels drive everything: one status label per issue says where it is, and the office acts on any change in its next cycle. An open issue with no status label is treated as `status:triage`. Every label, who sets and removes it, and the repo labels the office also honors are in **[Labels](LABELS.md)**.

## Blockers

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


## Practice suggestions

The office keeps suggesting better practices for the target repo:

- **A recurring review.** At most once every 24 hours, while fewer than three practice issues are open, the PM reviews the repo. It looks for drift between `AGENTS.md` and the code, gaps in the verify command, tests and CI, local-development friction, the design system, and fit with the [stack guides](stack/README.md) that apply to it. The automated readiness findings feed into it.
- **While working.** Any agent that notices something the repo should do better can add one `Practice:` issue to its verdict.

Suggestions are filed with `office:practice` and `blocked:human`, so they wait for you and show up in the "Office status" issue. Remove `blocked:human` to have the office do one, or close it to decline. Duplicates are skipped (see [Follow-up issues](#follow-up-issues)). To let the office act on suggestions without asking, set `practices_need_approval` to `false` in `.office/config.json`.


## Stop condition

Each cycle, the orchestrator checks whether any issue can still be acted on. When every open issue is blocked or done and no agent is running, the office goes idle. It writes the list of everything waiting on a human into the "Office status" issue (office decisions first, then by priority), then polls every 10 minutes for answers. With `--exit-when-idle`, it exits instead.


---
[← Back to the README](../README.md)
