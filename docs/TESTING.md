# Testing

How the office verifies every change before it merges, and how to test the office itself.

## How a change is verified

No PR merges until it has passed every step below. A failure at any step sends the issue back to an engineer, with the reason as a comment, and the third send-back in a row files a blocker instead. A PR is judged against its own issue: something the repo lacked before it, such as a verify command or a user manual, doesn't fail it unless the issue asks for it. Without a verify command, the tester runs the checks the repo's `AGENTS.md` documents.

1. **The engineer's own gate.** Before opening or updating a PR, the engineer merges the latest base branch, then runs the repo's verify command (`make verify` or `npm run verify`) until it passes. For anything users see, it also builds the docs site with `mkdocs build --strict`.
2. **A merge-conflict check.** Before a review or test, and again just before merging (another PR may have merged while this one was being tested), the office asks GitHub whether the PR merges cleanly. A conflicting PR goes straight back to an engineer, without spending a Codex run, and the conflict isn't counted as a failure.
3. **Code review (Codex).** A different model from the one that wrote the code reviews the diff for correctness, security, data safety (such as tenancy scoping, migrations and secrets), missing tests, and conformance with the repo's `AGENTS.md`. It posts its findings as a PR comment. The office runs under your GitHub account, which can't approve its own PRs, so the reviewer's verdict (`approve` or `changes`) decides whether the issue moves on.
4. **Testing (Codex).** The tester checks out the PR in its own worktree and:
   - merges the latest base branch; a conflict, or migrations that clash with the base branch (see the stack guide), is a failure
   - runs the full verify command from a clean state
   - checks every acceptance criterion the way a user would: it starts the stack, seeds demo data, and calls the API or runs the repo's UI smoke check
   - writes missing tests for the criteria and pushes them
   - for anything users see, runs the [UI and UX testing](#ui-and-ux-testing) below and checks that the user manual describes the change accurately
   - runs the impeccable detector on changed UI files and treats serious findings as failures
   - posts a PR comment listing each acceptance criterion as pass or fail, and how it was checked
   - stops every server it started; the office also stops anything left running in the worktree
5. **CI and merge.** After a `pass`, the office waits up to 30 minutes for the PR's CI checks, squash-merges, deletes the branch and closes the issue. If CI fails, the issue goes back to an engineer. If the repo has no CI, the local verification stands on its own.

After a release you approve, the default branch is verified once more before anything goes live, and the tester then checks the live site: it opens every page in `docs/manual/pages.json` on the production URL from `AGENTS.md`, and checks the released changes are there and work. It only reads the live site. A failure never rolls back on its own; it asks you (see [Releases](WORKFLOW.md#releases)).

Bugs a tester finds outside the issue's scope are filed as new issues. Problems with the office's own tools never go into the target repo's backlog.

## UI and UX testing

For any change users see, the tester captures every page listed in the repo's `docs/manual/pages.json` at desktop (1280px) and phone (360px) widths, into `docs/manual/screenshots/`:

- **With the repo's own `make screenshots`**, when it has one. It is preferred, because setting up states such as "empty" or "validation error" needs knowledge of the app, and it keeps the repo able to regenerate its manual without the office.
- **Otherwise with `office shoot`**, the office's [Playwright](https://playwright.dev/) runner. It can only open plain URLs, and ignores fields it doesn't understand.

Either way, the tester checks objectively for:

- pages that fail to load, or return an error status
- console errors, uncaught page errors and failed requests
- expected text that isn't visible
- sideways scrolling on a phone
- images without alt text (a warning)

Any of these on a page the PR touches is a failure. The tester also judges the screenshots against the design comment and `DESIGN.md`. It commits the screenshots to the PR, where GitHub shows image diffs. Before merging, the office posts the changed screens on the PR, and after merging, it posts them on the "Office status" issue for you to review. They also update the live [docs site](DOCS-SITE.md).

To run `office shoot` yourself, from a target repo with its app running:

```bash
uv run --project /path/to/product-development-office office shoot --base-url http://127.0.0.1:8000
```

## Testing the office itself

```bash
make verify                           # ruff + pytest + docs check: the definition of done
uv run pytest tests/test_planner.py   # one file
uv run pytest -k blocker              # tests matching a name
uv run playwright install chromium    # once, before the screenshot tests
```

| Tests | Cover |
|---|---|
| `tests/test_planner.py` | Which task each issue needs next: statuses, claims, priorities, dependencies, failures |
| `tests/test_orchestrator.py` | How verdicts are applied, using a fake GitHub and stubbed agents: labels, blockers, follow-ups, practices, waiting, conflicts, merging, screenshots, restarts |
| `tests/test_agents.py` | Verdict parsing, prompt rendering, auth parsing, and stopping leftover processes (with a real process) |
| `tests/test_workspace.py` | Git retries on lock contention |
| `tests/test_clean.py` | Folder naming, legacy migration with real git worktrees, local and GitHub cleanup |
| `tests/test_readiness.py` | The integration checklist |
| `tests/test_plan.py` | `office plan` output |
| `tests/test_databases.py` | Finding the target's Postgres from its compose config, per-repo and per-issue prefixes, and the guard against touching any database outside `office_` |
| `tests/test_containers.py` | Which containers, networks and volumes an issue owns, keeping containers that publish a port outside the lease, never failing a run, and the guard against touching anything outside `office_` (with a stand-in `docker`) |
| `tests/test_stacks.py` | Parsing stack guides, detecting them by file name and contents, and that every guide in `docs/stack/` is valid and listed |
| `tests/test_signature.py` | Signatures, the `gh` wrapper's argument rewriting and an end-to-end run against a stand-in `gh`, and that agent comments don't reset the failure count |
| `tests/test_ports.py` | Port blocks (free, unreserved, one per run), fixed sets claimed by one issue at a time, the `office-lease` command, and probing and stopping a real server |
| `tests/test_shoot.py` | `office shoot` against a real local server and browser |

The tests never call the real `claude`, `codex` or GitHub. Extend the fakes in `tests/test_orchestrator.py` instead.

### End-to-end on a sandbox repo

Unit tests can't show how real agents behave, so test changes to prompts or the loop on a throwaway repo before using them on a real project:

1. Create a small private repo that meets the [integration checklist](INTEGRATION.md), and check it with `uv run office check owner/sandbox`.
2. File a few issues that exercise the paths you changed. A useful set:
   - a small backend task, which should go straight to ready
   - a UI change, which should go to design and get screenshots
   - a request that conflicts with the documented scope, which should become a blocker
   - two issues where the second builds on the first, which should use `waiting`
3. Run `uv run office start owner/sandbox --exit-when-idle`, and watch it with `uv run office plan owner/sandbox` in another terminal.
4. Read the issue comments, PRs and the "Office status" issue. Then answer a blocker and approve a practice suggestion, and run it again.
