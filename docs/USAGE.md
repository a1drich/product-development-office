# Usage

How to install, run and steer the office day to day. For preparing a repo first, see the [integration guide](INTEGRATION.md).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12+ for you). After `uv sync`, run `uv run playwright install chromium` once for screenshots.
- [GitHub CLI](https://cli.github.com/) (`gh`), logged in with access to the target repo
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code), logged in with a Claude subscription
- [Codex CLI](https://github.com/openai/codex), logged in with a ChatGPT subscription

## Install and run

```bash
git clone https://github.com/a1drich/product-development-office && cd product-development-office
uv sync

uv run office check owner/name               # is the repo ready? (read-only)
uv run office check owner/name --file-issues # file an issue for each gap
uv run office start owner/name --dry-run     # show what the office would do
uv run office start owner/name               # run until blocked
```

Run with no repo, `office start` asks for one and remembers it in `.office/config.json`:

```
$ uv run office start
? Which GitHub repo should the office work on? (owner/name) acme/widget-app
✓ no API keys: none set
✓ gh: logged in
✓ claude: logged in (max)
✓ codex: logged in (ChatGPT)
✓ cloned acme/widget-app into workspace/acme__widget-app
✓ labels ready (14 created)
→ verify command: make verify
12:00:01 starting triage on #12 (pm)
```

Startup steps:

1. Read the target repo (`owner/name`) from the argument or the saved config, or ask for it.
2. Check that no API key is set, and that `gh`, `claude` (subscription login) and `codex` (ChatGPT login) are logged in. Startup refuses to continue otherwise.
3. Clone the repo into `workspace/`, which this project's git history doesn't track.
4. Create any missing office labels on the target repo.
5. Release any `status:in-progress` claims left over from a previous run (a fresh office has no agents running), then hand control to the orchestrator loop.

**Stopping and resuming.** Stop the office with Ctrl-C at any time, and run `office start` again to pick up where it left off. All state lives in GitHub, so:
- a step that was interrupted (triage, design, review or test) reruns from the start, because labels only move when an agent finishes;
- an interrupted engineer's claim is released at the next start, and any work it had pushed is kept;
- runs cut short by the shutdown aren't counted as failures.

| Command | What it does |
|---|---|
| `office check [repo] [--run-verify] [--file-issues]` | Checks a repo against the [integration checklist](INTEGRATION.md). `--run-verify` also runs its verify command on a fresh clone. `--file-issues` files one `status:triage` issue per gap, so fixing readiness becomes the office's first work. |
| `office labels [repo]` | Creates the office labels |
| `office shoot --base-url URL` | Run in a target repo with its app running: screenshots every page in `docs/manual/pages.json` at desktop and mobile width, and reports UX problems |
| `office plan [repo]` | Shows every open issue's status, priority and what happens next, in the order the office would take them. Read-only, so it's safe to run while the office is running. |
| `office clean [repo] [--github] [--yes]` | Removes a project's local folders and forgets it as the saved repo, keeping your settings. Refuses while the office or an agent is still running there. `--github` also deletes the office's labels, its `office/issue-*` branches without an open PR, and the status issue, after showing the plan and asking. |
| `office docs build\|serve [repo]` | Builds the target's MkDocs site with `--strict`, or serves it locally |
| `office start [repo] [--dry-run] [--exit-when-idle]` | Runs the office. `--dry-run` prints the plan and changes nothing. `--exit-when-idle` exits instead of polling once everything is blocked or done. |

Settings such as concurrency per role (`limits`), poll intervals and the claim timeout can be overridden in `.office/config.json`. The defaults are in `office/config.py`. The config is read at startup, so changes apply from the next `office start`.

## Day to day

1. **Start the office** in a terminal on your machine and leave it running: `uv run office start owner/name`.
2. **Ask for things** by opening GitHub issues on the target repo (see below).
3. **Check in** whenever suits you:
   - the **"Office status" issue** lists everything waiting on you
   - the **docs site** at `http://127.0.0.1:8787` shows the current product, with screenshots
   - **GitHub notifications** show progress comments, PRs, and the changed screens after each merge
   - **`office plan owner/name`** shows, in a second terminal, what every open issue is waiting for
4. **Answer what's waiting:** blockers and practice suggestions, each in under a minute (see below).
5. **Stop it** with Ctrl-C whenever you like. `office start` resumes where it left off.

## Building a feature

Open an issue on the target repo that describes the outcome you want, in plain language. You don't need to write a spec, acceptance criteria or a design; that's the office's job.

```bash
gh issue create --repo owner/name \
  --title "Let customers reorder a past order" \
  --body "Repeat customers keep rebuilding the same order by hand. From their order history, let them reorder in one tap. Most use the app on their phone."
```

Or use the "New issue" button on GitHub. What helps:

- **Say who it's for and why**, not how to build it. The PM checks it against `PRODUCT.md` and the docs, and the Designer works out the screens.
- **One outcome per issue.** The PM splits anything bigger into small issues and links them.
- **Mark urgency** with a priority label if it matters: `priority:p0` (most urgent) to `priority:p3`, or the repo's own `P0`..`P3`. Without one, the PM sets it.
- **Mention dependencies** if you know them ("Depends on #12"). The office waits for #12 to close before starting.
- **Leave the issue unlabelled.** Any open issue without a status label is picked up and triaged on the next cycle, usually within a minute.

What happens next, all visible as comments on the issue:

1. **Triage (PM):** rewrites the issue with a problem statement and acceptance criteria, then sets a priority. It may split the issue, park it until a dependency lands, or file a blocker if it needs a decision from you. A request that conflicts with the documented scope becomes a blocker asking whether to change the scope; it is never silently closed.
2. **Design (Designer)**, for anything users see: posts a design comment with the flows, states, copy, the user-manual entry and the screens to capture.
3. **Build (Engineer):** opens a PR that includes tests and the updated user manual, and passes the repo's verify command.
4. **Review (Codex):** posts its findings on the PR. Blocking findings send the work back to an engineer.
5. **Test (Codex):** runs everything locally, checks each acceptance criterion, and screenshots and UX-checks every page.
6. **Merge:** once CI is green, the office squash-merges, closes the issue, posts the changed screens on the PR and the status issue, and the docs site updates.

## Steering work in progress

| You want to | Do this |
|---|---|
| Answer a blocker | Comment with your decision on the blocker issue, then remove its `blocked:human` label. |
| Accept a practice suggestion | Remove `blocked:human` from the `Practice:` issue. |
| Decline a suggestion or drop a feature | Close the issue. |
| Pause one issue | Add `blocked:human`; remove it to resume. |
| Change what an issue asks for | Edit the issue or add a comment. Each role reads the issue and its comments when it starts its step, so the change applies from the next step on. |
| Make something urgent | Add `priority:p0`. |
| See what happens next | `uv run office plan owner/name`, in another terminal. It's read-only. |
| Re-do a step | Set the status label back, for example to `status:ready` to rebuild, or `status:triage` to re-scope. |

## Switching projects and cleaning up

To move to another project, run `office start owner/other-repo`. The new repo replaces the saved one in `.office/config.json`, and it gets its own folder under `workspace/`. Nothing carries over, because each project's state lives in its own GitHub issues.

What the office keeps locally, all gitignored:

| Path | What |
|---|---|
| `.office/config.json` | The saved repo and your setting overrides |
| `workspace/<owner>__<repo>/` | The main clone of the target |
| `workspace/<owner>__<repo>-worktrees/` | One worktree per issue being worked on |
| `workspace/<owner>__<repo>-mkdocs.log` | The live docs server's log |

Folders include the owner, so `acme/web` and `other/web` never collide. Folders from older versions, named after the repo alone, are moved to the new names automatically, worktrees included, the next time the office uses them. A folder still in use by a running office is never moved.

To clear out a project you're done with, stop the office, then:

```bash
uv run office clean owner/name            # local folders; forgets the saved repo, keeps settings
uv run office clean owner/name --github   # also the labels, office branches and status issue
```


---
[← Back to the README](../README.md)
