# Integrating an existing repo

This guide prepares an existing GitHub repo so the office can work on it. Most of the steps are repo hygiene that also helps human contributors.

Start by running the readiness check. It covers every item below that can be checked automatically:

```bash
uv run office check owner/name                # read-only report
uv run office check owner/name --run-verify   # also run the verify command on a fresh clone
uv run office check owner/name --file-issues  # file an issue per gap for the office to fix
```

Before you start, set up the machine that runs the office: [setup guide, part 1](SETUP.md#1-the-office-machine).

## Readiness checklist

The office can work on a repo once every box below is ticked. The steps that follow cover each one.

- [ ] `AGENTS.md` describes the commands, architecture and rules, and `CLAUDE.md` imports it
- [ ] One command runs every check: `make verify` or `npm run verify`
- [ ] A fresh clone runs locally with no third-party accounts
- [ ] Tests use their own database, so parallel agents don't collide
- [ ] The product and design docs live in the repo
- [ ] The impeccable design skill is committed to the repo
- [ ] An MkDocs site with a user manual and feature catalog at `docs/manual/`
- [ ] Issues are on and the office labels exist
- [ ] CI runs the same checks as the verify command
- [ ] Human-only actions (deploys, secrets, money) are written down

---

## 1. Write the agent brief

Every agent reads these files before touching anything. They are the most important part of the integration.

**`AGENTS.md`.** Put all agent guidance in this one file. Codex (the reviewer and tester) reads it directly, and Claude Code reads it through `CLAUDE.md`. A good starting point is to run `/init` in Claude Code at the repo root, then move the result into `AGENTS.md`. It should cover:
- how to install, run and test, including how to run a single test
- the big-picture architecture: how the apps fit together and where the risky logic lives
- conventions an agent would otherwise break, such as how querysets are scoped or which Tailwind version is used
- links to the deeper docs in `docs/`
- the working rules, for example:

```markdown
- Run `make verify` before calling any change done.
- One small PR per issue, with tests and doc updates in the same PR.
- Work in your own git worktree; never touch another agent's uncommitted work.
- Follow `docs/decisions.md`. If a decision seems wrong, file a blocker instead of changing it.
- Split any issue that mixes codeable work with owner-only work.
- Never deploy, release, edit production settings or change GitHub secrets.
```

**`CLAUDE.md`.** Make it a one-line import, so the two files can never disagree:

```markdown
# CLAUDE.md

@AGENTS.md
```

If the repo already has a long `CLAUDE.md`, move its content into `AGENTS.md` and replace it with the import.

**`docs/`.** At minimum, add a short product brief (who it's for, what it does, what it deliberately won't do) and a decision log. The PM uses the brief to judge scope, and the decision log stops agents from "fixing" deliberate tradeoffs.

## 2. Add one verify command

Agents treat a single command as the definition of done. Engineers run it before opening a PR, and testers run it again before merging. If the repo has no such command, add one.

With a Makefile:

```makefile
.PHONY: test lint typecheck lint-fe verify

test:
	cd api && uv run pytest -q

lint:
	cd api && uv run ruff check .

typecheck:
	cd app && npm run typecheck

lint-fe:
	cd app && npm run lint

# The full gate. Run this before calling a change done.
verify: lint test typecheck lint-fe
```

Or with npm workspaces, add `"verify": "./scripts/verify.sh"` to the root `package.json` and have that script run each stage in order and fail fast.

Things to check:
- **Typecheck explicitly.** Nuxt and Next.js production builds often skip type checking, so a passing build doesn't prove the types are right.
- **Keep the command quiet and fast.** Agents will run it many times. If the full suite takes minutes, document how to run a single test in `AGENTS.md`.
- **Exit non-zero on any failure.** Agents trust the exit code.

## 3. Make local development self-contained

The engineers and testers run everything on your machine, in parallel, without your accounts.

- **Compose file:** `docker-compose.yml` starts Postgres (and Redis if needed).
- **Env defaults:** `.env.example` works as-is for local development. Add a `make env` target that copies it to `.env` without overwriting an existing one.
- **Mocked external services:** put each one (payments, OAuth, messaging) behind a flag such as `PAYMENTS_MOCK=true`, so the whole product runs end to end offline.
- **Demo data:** a `seed_demo` management command (`make seed`) creates realistic data, so the tester can exercise real flows.
- **Separate test database:** tests use their own database, and its name can be overridden per run, for example `TEST_DB_NAME=myapp_test_agent2`. Several agents running the suite at once must not share one.
- **Configurable ports:** dev server ports can be set from env vars, so two worktrees can run at the same time.

To check: clone the repo into a new folder, then run `make env install up migrate seed verify`. It should pass with no manual steps.

## 4. Put the design system in the repo

The Designer writes markdown design documents and engineers build from them, so the existing visual system has to be written down:

- `PRODUCT.md`: the users, the conditions they use the product in (device, connection, language) and the tone of voice
- `DESIGN.md` or `docs/design-system.md`: tokens, shared components, layout and typography rules

If the frontend uses design tokens, a script that flags raw colors outside the token system makes a cheap addition to `verify`.

### Install impeccable

The Designer plans UI work with the [impeccable](https://github.com/pbakaus/impeccable) design skill, engineers use it for UI changes, and the tester runs its detector. Install it at the repo root and **commit** the result, because the agents work from fresh clones:

```bash
npx skills add pbakaus/impeccable
git add .claude/skills/impeccable .agents/skills/impeccable
git commit -m "Add the impeccable design skill"
```

If `PRODUCT.md` or `DESIGN.md` is missing, impeccable can write them: in Claude Code, ask it to run impeccable's `init` command (product context) and its `document` command (the design system, generated from the existing code).

### Add the docs site and user manual

The office delivers an MkDocs site with every change, and its user manual is how you review what was built. Set up the skeleton once. After that, the agents keep it current.

`mkdocs.yml`:

```yaml
site_name: Widget App
theme:
  name: material
nav:
  - Home: README.md
  - User manual: manual/README.md
  - Decisions: decisions.md
```

`docs/manual/README.md`, the feature catalog and user manual:

```markdown
# User manual

## Home page

Lists your notes, newest first. Tap a note to open it.

| Desktop | Mobile |
|---|---|
| ![Home, desktop](screenshots/home-desktop.png) | ![Home, mobile](screenshots/home-mobile.png) |
```

`docs/manual/pages.json`, the pages to screenshot (`expect` is text that must be visible):

```json
{"pages": [{"name": "home", "path": "/", "expect": "Notes"}]}
```

Add a `make screenshots` target that seeds each page's state and captures it at desktop and mobile widths. Testers prefer it. Without one, they fall back to `office shoot`, which can only open plain URLs. Then capture the first screenshots with the app running, and make the docs build part of the verify command:

```bash
uv run --project /path/to/product-development-office office shoot --base-url http://127.0.0.1:8000
uvx --with mkdocs-material mkdocs build --strict   # add to `make verify`
```

## 5. Set up GitHub

### Labels

Create the office labels. This is safe to re-run, because `--force` updates labels that already exist:

```bash
REPO=owner/name

for l in triage design ready in-progress in-review testing done; do
  gh label create "status:$l" --repo "$REPO" --color 0E8A16 --force
done
gh label create "blocked:human" --repo "$REPO" --color B60205 --force \
  --description "Waiting for a human decision"
for p in 0 1 2 3; do
  gh label create "priority:p$p" --repo "$REPO" --color FBCA04 --force
done
```

`office labels owner/name` creates them too, and `office start` creates any that are missing. If the repo already uses a `blocked` label for owner-only work, or `P0`..`P3` for priority, keep them: the office treats `blocked` like `blocked:human`, and `P0`..`P3` like `priority:p0`..`p3`.

### Repo settings

```bash
gh repo edit "$REPO" --enable-issues --delete-branch-on-merge
```

- **Branch protection:** protect `main` from force-pushes and deletion. Agents merge with `gh pr merge` only.
- **CI:** add a workflow that runs the same checks as `verify` on pull requests. The tester waits for it before merging.
- **Workflow scope:** if agents should be allowed to edit `.github/workflows/`, the `gh` token needs the `workflow` scope: `gh auth refresh -h github.com -s workflow`.

## 6. Write down what only a human can do

Agents file a blocker whenever they hit one of these, so list them explicitly in `AGENTS.md` or `docs/OWNER-TODO.md`. Typical items:

- deploying or releasing (`make release` and similar)
- production settings, secrets, DNS and third-party dashboards
- anything that costs money or signs a contract
- legal, privacy and brand copy
- reversing a documented decision

## 7. Prepare the backlog

- Label existing open issues `status:triage`. The PM will scope them, add acceptance criteria and set priorities.
- Close stale issues first, so the PM doesn't spend effort on them.
- For a repo with no issues, open one issue describing the next goal, such as "v1 launch: what's missing". The PM breaks it down.

```bash
gh issue list --repo "$REPO" --state open --limit 500 --json number --jq '.[].number' |
  xargs -I{} gh issue edit {} --repo "$REPO" --add-label status:triage
```

## 8. Start the office

```bash
uv run office start owner/name --dry-run   # what it would do, changing nothing
uv run office start owner/name
```

On the first run, watch the PM's triage before letting engineers loose. Check that it read the brief correctly, that issues are small, and that blockers are real decisions rather than guesses it should have made itself.

While the office runs:

- **Answering a blocker:** comment on the blocker issue with your decision and remove `blocked:human`. The PM picks it up on the next cycle.
- **Steering:** open an issue, or edit an issue's labels or priority. The office keeps no state outside GitHub, so your changes take effect immediately.
- **Practice suggestions:** the office keeps filing `Practice:` issues with improvements for the repo, such as stale docs, missing tests or a slow verify command. They wait for you: remove `blocked:human` to accept one, or close it to decline.
- **Reviewing the product:** while the office runs, the target's docs site is live at `http://127.0.0.1:8787` and refreshes after every merge. Changed screens are posted on each PR and on the "Office status" issue.
- **Seeing what's waiting on you:** when the office goes idle, it lists every blocked issue in the "Office status" issue.
- **Pausing:** stop the `office` process with Ctrl-C, and run `office start` again to resume. Interrupted steps rerun, and leftover engineering claims are released at startup.

## Removing the office

Stop the process, then run `uv run office clean owner/name --github`. It shows its plan and asks before deleting the office's labels, the `office/issue-*` branches that have no open PR, and the "Office status" issue, and then removes the local folders. The manual equivalent is below. Nothing else in the repo depends on the office: the brief, the verify command, the docs site and the user manual are useful on their own. For the local cleanup, see [Switching projects and cleaning up](../README.md#switching-projects-and-cleaning-up).

```bash
for l in $(gh label list --repo "$REPO" --json name --jq '.[].name | select(startswith("status:") or startswith("priority:") or startswith("office:") or . == "blocked:human")'); do
  gh label delete "$l" --repo "$REPO" --yes
done

# branches of PRs that never merged
git ls-remote --heads "https://github.com/$REPO" 'office/issue-*' | awk '{print $2}' |
  sed 's#refs/heads/##' | xargs -I{} gh api -X DELETE "repos/$REPO/git/refs/heads/{}"

# the status issue
gh issue close "$(gh issue list --repo "$REPO" --label office:status --json number --jq '.[0].number')" --repo "$REPO"
```
