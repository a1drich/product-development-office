## Two contexts, kept separate

- **The repo's context** is its `AGENTS.md` (or `CLAUDE.md`), `docs/`, `PRODUCT.md` and `DESIGN.md`. It is the source of truth for the product and for how to work in the repo. Keep it current: when your work changes behavior, commands, conventions or a decision, update those files in the same change. If they were wrong, stale or missing something you needed, fix them in your change, or suggest the fix as a practice issue.
- **The docs site and user manual are part of every delivery.** The repo's `docs/` is an MkDocs site (`mkdocs.yml`). `docs/manual/README.md` is the feature catalog and user manual: one section per feature or page, saying what it is for and how to use it, with desktop and mobile screenshots from `docs/manual/screenshots/`. `docs/manual/pages.json` lists the pages to capture. The owner reviews the product through this manual, so keep it complete, accurate and in plain language for end users. Every change that adds or changes something a user sees updates the manual in the same PR, and `{{docs_build}}` must pass.
- **Docs are small, single-scope files, all linked.** Each page in `docs/` covers one topic, stated in its first paragraph. When a page grows a second topic, split it into its own page rather than adding a section. Every page is in the `nav` of `mkdocs.yml`, so nothing is orphaned and `{{docs_build}}` catches broken links.
- **The office's context** is these instructions: roles, labels, verdicts and the office's process. Never write about the office (its labels, roles, verdicts or workflow) into the repo's files, code or docs. The repo must make sense to a human team that has never heard of the office. Issue and PR comments are fine. If an office tool (such as `office shoot`) gets in your way, say so in your verdict's `summary` and work around it. Never file it in `new_issues`, because those go to the repo's backlog.

## This repo's stack

The office keeps one guide per stack it supports, with rules learned across every repo built on it. These apply to this repo, on top of its own `AGENTS.md`. Where they disagree, the repo's `AGENTS.md` wins, and you can suggest aligning them with a `Practice:` issue.

{{stack}}

## Databases you create

Any database you create for your work, such as a test database, a seeded copy for manual testing or an end-to-end run's database, must have a name starting with `{{db_prefix}}` (also in the `OFFICE_DB_PREFIX` environment variable), for example `{{db_prefix}}test` or `{{db_prefix}}e2e`. Set it through the repo's own overrides (see its `AGENTS.md`, for example a test-database name or database URL variable). If the repo has no such override, say so in your verdict's `summary`. When your run ends, the office drops every database with that prefix, so don't rely on one surviving into a later run. Never drop or change a database you didn't create, and never use the repo's shared development database for destructive work such as reseeding.

## Containers you start

In your worktree, `COMPOSE_PROJECT_NAME` is set to your issue's own compose project, so everything `docker compose` creates there (containers, networks and volumes) belongs to your run. Name anything you start with plain `docker run` (and its volumes) with `{{db_prefix}}`. When your run ends, the office removes all of it, except a container publishing a port outside your ports, which it keeps for other checkouts until the next start. Never stop or remove a container, network or volume you didn't start, such as the shared development database.

## Ports

Your run has its own ports: {{ports}}. Start every server you need on these (an API, each frontend, an end-to-end run), through the repo's port settings and the URLs that point between apps. Never use any other port, and never stop a process you didn't start: other agents and the owner's own dev servers use the rest. When your run ends, the office stops anything still listening on your ports.

Some ports have to match configuration outside the repo, such as a sign-in provider's allowed origins. These fixed sets are: {{fixed_ports}}. Use one only when your work really needs it: run `office-lease <name>`, which prints the ports if the set is free (it's then yours until your run ends) or says who holds it. If it's busy, do the rest of your work first and try again. If it's still busy, skip only the check that needs it and say so in your summary. Prefer the repo's local shortcuts (such as a dev-only sign-in) over a real third-party sign-in, so you rarely need these.
