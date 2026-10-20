# Workflow

Who does what, and how an issue moves from request to merge and then into a release. The orchestrator polls the target repo, finds issues in each state and dispatches them to the matching role. For how a PR is verified, see [Testing](TESTING.md).

## The team

| Role | Runs on | Responsibilities |
|---|---|---|
| **Product Manager** | Claude Code (Claude subscription) | Reads the repo and its open issues, writes and keeps the backlog, breaks epics into scoped issues with acceptance criteria, sets priorities, files blockers for human decisions, and decides when an issue is done. |
| **Designer** | Claude Code (Claude subscription) + [impeccable](https://github.com/pbakaus/impeccable) | Uses impeccable's `shape` command to turn product issues into markdown design documents (flows, screens, states, copy, tokens and components). Each one includes the user-manual entry, the screens to capture and an implementation prompt for engineers, and is posted on the issue before engineering starts. |
| **Engineer** (1..n) | Claude Code (Claude subscription) | Picks up `ready` issues, works in an isolated git worktree, implements the change (using impeccable for any UI work), runs the verify command and opens a PR linked to the issue. |
| **Reviewer** | Codex CLI (ChatGPT/Codex subscription) | Reviews every PR for correctness, security and maintainability. It either approves or requests changes, and changes go back to an engineer. |
| **Tester** | Codex CLI (ChatGPT/Codex subscription) | Checks out approved PRs locally and verifies them against the acceptance criteria: merges in the base branch, runs the full verify command, writes missing tests, exercises the change, screenshots and UX-checks every page with [Playwright](https://playwright.dev/) (`office shoot`), checks the user manual and runs the impeccable detector on UI changes. If it passes, the office merges the PR; otherwise it goes back to an engineer, and any bugs found are filed as issues. After each release you approve, it checks the live site. |

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

Any agent can ask for follow-up issues in its verdict: bugs it found, work it split off, or practice suggestions. The office files them with `status:triage`. To avoid duplicates, every agent's prompt lists the open issues, and agents point at an existing issue (or comment on it) instead of filing a new one. As a backstop, the office skips a follow-up whose title matches an open issue's, ignoring case, punctuation, articles and a `Practice:` prefix. Agents running side by side only see the issues open when they started, so a `Practice:` suggestion is also checked against the practice issues open at the moment it's filed: if one covers the same topic (most of the shorter title's words appear in the other), the suggestion is added to it as a comment instead, and if three or more are already open, it isn't filed.

## Labels

Labels drive everything: one status label per issue says where it is, and the office acts on any change in its next cycle. An open issue with no status label is treated as `status:triage`. Every label, who sets and removes it, and the repo labels the office also honors are in **[Labels](LABELS.md)**.

## Blockers

Anything that needs human input becomes a blocker. Examples are product direction, ambiguous requirements, credentials or access, spending money, legal or brand questions, and irreversible actions such as changing production settings. Merging a fully tested PR is *not* a blocker. Releasing isn't one either: it has its own approval (see [Releases](#releases)).

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

If an agent fails on the same issue three times in a row, for example by crashing, timing out or returning no verdict, the office files a blocker for it instead of retrying forever. The same goes for an issue that review or testing sends back to an engineer three times in a row: work that keeps coming back usually needs something the engineer can't provide, such as a gap only another issue fills.

## Circular dependencies

Issues can end up waiting on each other, so none of them ever starts. The office guards against this in three ways:

- **A circular wait is refused.** If an agent returns `waiting` on an issue that already waits, directly or through others, on the agent's own issue, the office doesn't park it. It records the run as failed, with the reason, so the next run goes ahead without waiting or splits off the part that needs the other issue.
- **An existing cycle is broken.** If waiting issues already form a cycle (say, from before this check), the office releases the most urgent one, with a comment saying why, so work goes on.
- **Testers judge a PR against its own issue.** Something the repo lacked before the PR, such as a verify command or a user manual, doesn't fail it unless its issue asks for it. Otherwise a PR could never pass until another issue lands, while that issue waits for the PR. If it happens anyway, the send-back limit above turns it into a blocker.


## Releases

Deploying is always your decision, and a merge never triggers one. The office prepares each release, you approve it, and the office runs it and checks the result. This applies to repos with a release command (`make release` or `npm run release`; see the [setup guide](SETUP.md#2-preparing-a-target-repo)). Without one, the office merges and never releases.

```
merges ──▶ "Release" issue (office:release, blocked:human): the changes not live yet
               │ you add release:approved (on GitHub, or `office release owner/name`)
               ▼
           office: checks a repo admin added it and the default branch hasn't moved,
                   runs verify on it, then the release command
               │
               ▼  status:testing
           Tester (Codex): checks the live site ──pass──▶ closed
               │ fail
               ▼  blocked:human
           you add rollback:approved ──▶ office runs the rollback command ──▶ pending again
           (or close the issue to keep the release)
```

- **One release issue at a time.** A merge that changes something users can see (it updates `docs/manual/`) opens the "Release" issue if none is waiting. Every later merge is added to its list until you approve it, so a busy day is one release to approve, not one per PR. A merge nobody can see opens nothing, and goes out with the next release.
- **What you approve is what ships.** The issue records the commit its list was written at. If the default branch has moved by the time the office runs the release, it takes your approval off and asks you to look again. A failing verify on the default branch also stops the release before anything goes live.
- **Only you approve.** The office acts on `release:approved` and `rollback:approved` only when a repo admin added them, and its `gh` wrapper refuses to let an agent add them.
- **It never rolls back on its own.** When the live check fails, the issue waits for you with the tester's findings. Add `rollback:approved` to have the office run the rollback command (`make rollback REF=<commit>`, given the last release's commit), or close the issue to keep the release. After a rollback, the same changes wait for approval again, together with the fix once it merges.
- **One comment per step.** The release issue's body is updated in place as merges land, which sends no notifications. You get a comment when the release runs or is refused, and when the live check reports.

## Practice suggestions

The office keeps suggesting better practices for the target repo:

- **A recurring review.** At most once every 24 hours, while fewer than three practice issues are open, the PM reviews the repo. It looks for drift between `AGENTS.md` and the code, gaps in the verify command, tests and CI, local-development friction, the design system, and fit with the [stack guides](stack/README.md) that apply to it. The automated readiness findings feed into it.
- **While working.** Any agent that notices something the repo should do better can add one `Practice:` issue to its verdict.

Suggestions are filed with `office:practice` and `blocked:human`, so they wait for you and show up in the "Office status" issue. Remove `blocked:human` to have the office do one, or close it to decline. Duplicates are skipped (see [Follow-up issues](#follow-up-issues)). To let the office act on suggestions without asking, set `practices_need_approval` to `false` in `.office/config.json`.


## Stop condition

Each cycle, the orchestrator checks whether any issue can still be acted on. When every open issue is blocked or done and no agent is running, the office goes idle. It writes the list of everything waiting on a human into the "Office status" issue (office decisions first, then by priority), then polls every 10 minutes for answers. With `--exit-when-idle`, it exits instead.


---
[← Back to the README](../README.md)
