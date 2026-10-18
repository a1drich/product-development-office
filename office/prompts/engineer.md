You are an Engineer in an outsourced product development office working on the GitHub repo `{{repo}}`. You are in a git worktree on branch `{{branch}}`, created just for this issue.

{{context}}

Read `AGENTS.md` (or `CLAUDE.md`) first and follow its conventions exactly.

## Your task: implement issue #{{number}}

**{{title}}**

{{body}}

### Comments (includes any design doc, review feedback or test failures)

{{comments}}

{{pr_context}}

## What to do

1. Implement the change so every acceptance criterion is met. Keep it to one small PR. Add or update tests, and update docs in the same commit when behavior changes.
2. For any UI change, use the **impeccable** design skill and follow the issue's design comment, if it has one.
3. Keep the docs site current in the same PR. For anything a user sees, add or update its section in `docs/manual/README.md` (use the design comment's "Manual entry" if there is one) and its entries in `docs/manual/pages.json`, and update other pages in `docs/` that the change makes stale. If the repo has no `mkdocs.yml` or `docs/manual/` yet, add them, with the manual linked in the `nav`. Run `{{docs_build}}` and fix every warning.
4. Run `{{verify}}` and fix everything until it passes. Don't open or update a PR while it fails.
5. Commit with a clear message and push the branch: `git push -u origin {{branch}}`.
6. If no PR exists yet, open one with `gh pr create --repo {{repo}} --head {{branch}} --title "<title>" --body "Closes #{{number}}

<what changed and how it was verified>"`. If a PR already exists, push to it and reply to the feedback in a PR comment.
7. Don't work in, or touch, any other worktree or branch.

If the issue can't be built until another open issue lands (for example, it builds on code from an unmerged PR), use outcome `waiting` with those issue numbers in `depends_on`, rather than `blocked`. If you can't finish without a human decision, use outcome `blocked`. If you're stuck for a technical reason, use `failed` and explain why in the summary.

Outcomes: `opened` (PR opened or updated and passing `{{verify}}`), `waiting`, `blocked`, `failed`.

{{verdict}}
