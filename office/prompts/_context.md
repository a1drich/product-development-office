## Two contexts, kept separate

- **The repo's context** is its `AGENTS.md` (or `CLAUDE.md`), `docs/`, `PRODUCT.md` and `DESIGN.md`. It is the source of truth for the product and for how to work in the repo. Keep it current: when your work changes behavior, commands, conventions or a decision, update those files in the same change. If they were wrong, stale or missing something you needed, fix them in your change, or suggest the fix as a practice issue.
- **The office's context** is these instructions: roles, labels, verdicts and the office's process. Never write about the office (its labels, roles, verdicts or workflow) into the repo's files, code or docs. The repo must make sense to a human team that has never heard of the office. Issue and PR comments are fine.
