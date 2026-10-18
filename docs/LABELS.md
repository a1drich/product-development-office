# Labels

Every GitHub label the office uses, what it means, who sets and removes it, and what the office does about it. The labels are the office's entire state: change one, and the office acts on the change in its next cycle.

The office creates the labels below on the target repo at startup (or with `office labels owner/name`), and `office clean --github` deletes them. They are defined in `office/labels.py`, and a test keeps this page in sync with it. For how issues move between the labels, see [Workflow](WORKFLOW.md).

## Status labels

Exactly one status label per issue says where it is in the flow. The office moves them; you can set one by hand to redo a step.

| Label | Color | Meaning | Set by | Next |
|---|---|---|---|---|
| `status:triage` | `#C5DEF5` | New or unscoped; the PM writes acceptance criteria | The office, when it starts triaging an issue with no status label or files a follow-up; `office check --file-issues` | PM triages it |
| `status:design` | `#D4C5F9` | Needs a design doc before engineering | The office, after the PM's `design` verdict | Designer designs it |
| `status:ready` | `#0E8A16` | Fully specified; an engineer can pick it up | The office, after a PM or Designer `ready` verdict, a review asking for changes, a failed test, a merge conflict, a failed CI check, or a released claim | An engineer builds it |
| `status:in-progress` | `#FBCA04` | An engineer is working on it | The office, when an engineer starts; it also assigns the issue and posts a claim comment | The engineer's verdict moves it on. At startup, or after `claim_ttl_minutes` with no agent running, the claim is released back to `status:ready`. |
| `status:in-review` | `#1D76DB` | PR open, waiting for Codex review | The office, after an engineer's `opened` verdict | Codex reviews the PR |
| `status:testing` | `#5319E7` | PR approved, waiting for Codex testing | The office, after the reviewer's `approve` verdict | Codex tests it, then the office merges it after CI |
| `status:done` | `#0E8A16` | Verified locally and merged | The office, after merging | The office closes the issue if the merge didn't |

An open issue with **no status label** is treated as `status:triage`, so issues you open are picked up without labelling them.

## Waiting on a human

| Label | Color | Meaning | Set by | Removed by |
|---|---|---|---|---|
| `blocked:human` | `#B60205` | Waiting for a human decision. Agents skip the issue until it is removed. | The office, on a blocker issue and on the issue it blocks; on a practice suggestion awaiting approval; and after a step fails three times in a row. You can add it to pause any issue. | **You**: remove it to answer a blocker, approve a suggestion or resume a paused issue. The office removes it from the blocked issues once the PM has applied your answer. |
| `office:blocker` | `#B60205` | A decision issue the office filed, written to be answered in under a minute | The office, on each blocker it files | The office closes the blocker once the PM has applied your answer. If the answer is incomplete, the office puts `blocked:human` back and comments with what's still needed. |

To answer a blocker, comment with your decision on the `office:blocker` issue, then remove its `blocked:human` label. See [Blockers](WORKFLOW.md#blockers).

## Office bookkeeping

| Label | Color | Meaning | Set by | Removed by |
|---|---|---|---|---|
| `office:waiting` | `#EDEDED` | Waiting for other issues to close, such as a feature that builds on an unmerged PR. Not a human decision. | The office, after a `waiting` verdict; a comment records which issues it waits for | The office, once all of those issues are closed; the issue then continues from its status label. Removing it yourself makes the office proceed immediately. |
| `office:practice` | `#C2E0C6` | A suggested improvement to how the repo is built or maintained | The office, on every `Practice:` issue an agent or the practices review suggests. It also gets `blocked:human` while `practices_need_approval` is on (the default). | Stays while the issue is open. While three or more are open, the daily practices review pauses. |
| `office:status` | `#BFDADC` | The single "Office status" issue: everything waiting on you, the docs-site link, and changed screens after each merge | The office, on the issue it creates for this | Never; `office clean --github` closes the issue |

## Priority

| Label | Color | Meaning |
|---|---|---|
| `priority:p0` | `#FBCA04` | Most urgent; worked first |
| `priority:p1` | `#FBCA04` | High |
| `priority:p2` | `#FBCA04` | Normal |
| `priority:p3` | `#FBCA04` | Low |

The PM sets a priority during triage, and you can set or change one at any time. Within each role, the office takes the lowest number first, then the oldest issue. Issues without a priority go last.

## Labels from the target repo

The office honors two kinds of labels a repo may already use, and never creates, removes or deletes them:

| Repo label | Treated as |
|---|---|
| `blocked` | `blocked:human`: the office skips the issue until you remove it. The office never removes it. |
| `P0`, `P1`, `P2`, `P3` (any case) | `priority:p0` to `priority:p3` |

All other labels, such as `bug` or `enhancement`, are ignored by the office and left alone by `office clean`.

---
[← Back to the README](../README.md)
