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
uv run office start owner/a owner/b owner/c  # several repos in one office (see below)
```

Run with no repo, `office start` asks for one or more and remembers them in `.office/config.json`:

```
$ uv run office start
? Which GitHub repos should the office work on? (owner/name, several separated by spaces) acme/widget-app
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

1. Read the target repos (`owner/name`) from the arguments or the saved config, or ask for them.
2. Check that no API key is set, and that `gh`, `claude` (subscription login) and `codex` (ChatGPT login) are logged in. Startup refuses to continue otherwise.
3. Clone each repo into `workspace/`, which this project's git history doesn't track.
4. Create any missing office labels on each target repo.
5. Release any `status:in-progress` claims left over from a previous run (a fresh office has no agents running).
6. If the [impeccable](https://github.com/pbakaus/impeccable) design skill isn't committed to the repo, file an "Add the impeccable design skill" issue labelled `status:ready` and `priority:p0`, unless one is already open. An engineer installs and commits it in a PR that is reviewed and tested like any other, and design work waits until the issue closes. The office never commits to the target itself.
7. Hand control to the loop, which runs every repo together.

## Stopping and resuming

| To | In the office's terminal | From another terminal |
|---|---|---|
| **Stop once running agents finish** (drain): start nothing new, let each running agent finish its step, apply the verdicts, then exit | Ctrl-C | `office stop owner/name` |
| **Stop now**: end the running agents and exit | Ctrl-C a second time | `office stop owner/name --now` |

`office stop` waits until the office has exited (add `--no-wait` to return straight away). A drain can take as long as the slowest running step, and a step waiting on CI can take up to 30 minutes, so use `--now` if you can't wait.

Run `office start` again to pick up where it left off. All state lives in GitHub, so:
- a drained office leaves nothing half done;
- a step stopped with `--now` (triage, design, review or test) reruns from the start, because labels only move when an agent finishes, and it isn't counted as a failure;
- a stopped engineer's claim is released at the next start, and any work it had pushed is kept.

Only one office can run per repo. `office start` refuses if another is already running on it. When one office runs several repos, stopping it stops all of them (`office stop` on any of them says which).

| Command | What it does |
|---|---|
| `office check [repo] [--run-verify] [--file-issues]` | Checks a repo against the [integration checklist](INTEGRATION.md). `--run-verify` also runs its verify command on a fresh clone. `--file-issues` files one `status:triage` issue per gap, so fixing readiness becomes the office's first work. |
| `office labels [repo]` | Creates the office labels |
| `office shoot --base-url URL` | Run in a target repo with its app running: screenshots every page in `docs/manual/pages.json` at desktop and mobile width, and reports UX problems |
| `office stop [repo] [--now] [--no-wait]` | Stops a running office once its agents finish their step, or immediately with `--now` |
| `office plan [repo]` | Shows every open issue's status, priority and what happens next, in the order the office would take them, and the ports each running agent holds. Read-only, so it's safe to run while the office is running. |
| `office release [repo] [--rollback] [--yes]` | Shows the open release issue's changes and, once you confirm, approves it by adding `release:approved` as you. `--rollback` approves rolling back a release whose live check failed. The running office then does the rest (see [Releases](WORKFLOW.md#releases)); adding the label on GitHub does the same. |
| `office clean [repo] [--github] [--yes]` | Removes a project's local folders and the throwaway databases, containers, networks and volumes its agents created, and forgets it as the saved repo, keeping your settings. Refuses while the office or an agent is still running there. `--github` also deletes the office's labels, its `office/issue-*` branches without an open PR, and the status issue, after showing the plan and asking. |
| `office docs build\|serve [repo]` | Builds the target's MkDocs site with `--strict`, or serves it locally |
| `office start [repo ...] [--dry-run] [--exit-when-idle]` | Runs the office on one or more repos, in one process (see [Several repos at once](#several-repos-at-once)). With none, it runs the repos it last started. `--dry-run` prints the plan and changes nothing. `--exit-when-idle` exits instead of polling once everything is blocked or done. |

Settings such as concurrency per role (`limits`), poll intervals and the claim timeout can be overridden in `.office/config.json`, and settings that belong to one repo go under `repos` (see [Several repos at once](#several-repos-at-once)). If a target's local Postgres isn't the one its compose file describes (another project already holds that port, say), set that repo's `database_url` to `postgres://user:password@host:port/dbname` so the office drops agents' throwaway databases in the right place. The defaults are in `office/config.py`. The config is read at startup, so changes apply from the next `office start`.

Ports have their own settings. Agents only use ports the office leases them (see [Architecture](ARCHITECTURE.md)), so your own dev servers and the agents never collide:

| Setting | Default | What it's for |
|---|---|---|
| `agent_ports` | `"40000-44999"` | The range agents' port blocks come from |
| `ports_per_agent` | `10` | Ports in each run's block |
| `reserved_ports` | `["3000-3099", "5173-5199", "8000-8099"]` | Your ports: agents never get these |
| `fixed_ports` | `{}` | Named sets that must match outside configuration, such as `{"oauth": [3011, 3012]}` for a sign-in provider's allowed origins. One agent at a time claims a set. |

## Several repos at once

One office can run several repos you own: `uv run office start owner/a owner/b owner/c`. It remembers them, so a plain `office start` runs the same set next time. They share the machine's Claude and ChatGPT subscriptions, so:

- **`limits` cover every repo together.** With `"engineer": 2`, at most two engineers run at once across all the repos, not two each.
- **The most urgent work goes first, whichever repo it's in.** A `priority:p0` issue in one repo starts before a `priority:p2` in another. Equally urgent work takes turns between the repos.
- **A usage limit pauses that role everywhere,** since every repo was drawing on the same subscription.
- **Each repo keeps its own state:** its clone, worktrees, status issue, release issue and docs site. The docs sites get one port each, from `docs_port` up (8787, 8788, ...); the office logs each one's URL, and each repo's status issue links its own.
- **Log lines start with the repo** they're about, such as `[owner/a] #12 -> status:in-review`.
- **Ports come from one pool.** Agents in any repo never get a port another agent holds, even one leased by a separate `office start` on the same machine.

Settings for one repo go under `repos`, keyed by `owner/name`. Any setting can be set there except the ones that describe the machine (`limits`, `poll_seconds`, `idle_poll_seconds`, `rate_limit_pause_minutes`, `agent_ports`, `ports_per_agent` and `reserved_ports`). `office start` refuses a config that tries:

```json
{
  "limits": {"engineer": 2},
  "repos": {
    "owner/a": {"database_url": "postgres://app:app@localhost:5547/app",
                "fixed_ports": {"oauth": [3011, 3012]}},
    "owner/b": {"practices_need_approval": false}
  }
}
```

`office plan`, `office release`, `office stop` and the other commands still take one repo.

## Day to day

1. **Start the office** in a terminal on your machine and leave it running: `uv run office start owner/name`.
2. **Ask for things** by opening GitHub issues on the target repo (see below).
3. **Check in** whenever suits you:
   - the **"Office status" issue** lists everything waiting on you
   - the **docs site** at `http://127.0.0.1:8787` shows the current product, with screenshots
   - **GitHub notifications** show progress comments, PRs, and the changed screens after each merge
   - **`office plan owner/name`** shows, in a second terminal, what every open issue is waiting for
4. **Answer what's waiting:** blockers and practice suggestions, each in under a minute (see below).
5. **Tell the office's posts from yours.** The office uses your GitHub login, so its comments show your name. Each one ends with a line naming the role that wrote it, such as `🤖 Reviewer (Codex) · product development office` (details in [Architecture](ARCHITECTURE.md)).
6. **Stop it** with Ctrl-C (or `office stop owner/name`) whenever you like. It finishes what's running first. `office start` resumes where it left off.

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

To move to another project, run `office start owner/other-repo`. The new repo replaces the saved ones in `.office/config.json`, and it gets its own folder under `workspace/`. Nothing carries over, because each project's state lives in its own GitHub issues.

What the office keeps locally, all gitignored:

| Path | What |
|---|---|
| `.office/config.json` | The saved repos and your setting overrides |
| `workspace/<owner>__<repo>/` | The main clone of the target |
| `workspace/<owner>__<repo>-worktrees/` | One worktree per issue being worked on |
| `workspace/<owner>__<repo>-mkdocs.log` | The live docs server's log |
| `workspace/leases/` | The ports running agents hold, one file per lease named after its repo, shared by every office on the machine. `office plan` shows a repo's; each start clears its repos' leftovers. |
| `workspace/<owner>__<repo>.pid` | The running office's process id, used by `office stop`; removed when it exits |

Folders include the owner, so `acme/web` and `other/web` never collide. Folders from older versions, named after the repo alone, are moved to the new names automatically, worktrees included, the next time the office uses them. A folder still in use by a running office is never moved.

To clear out a project you're done with, stop the office, then:

```bash
uv run office clean owner/name            # local folders; forgets the saved repo, keeps settings
uv run office clean owner/name --github   # also the labels, office branches and status issue
```


---
[← Back to the README](../README.md)
