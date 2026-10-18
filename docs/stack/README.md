# Stack guides

What the office knows about each tool a target repo might be built with, one guide per tool, and how to contribute a new one. Everything the office learns that only applies to one stack lives in that stack's guide, so supporting a new stack means adding a guide, not changing the office.

## Supported stacks

| Guide | Layer | Detected by |
|---|---|---|
| [Django](DJANGO.md) | Backend | `manage.py` |
| [Next.js](NEXTJS.md) | Frontend | `next.config.*` |
| [Nuxt](NUXT.md) | Frontend | `nuxt.config.*` |
| [Tailwind CSS](TAILWIND.md) | Styling | `tailwindcss` in a `package.json` |
| [Postgres](POSTGRES.md) | Data | a `postgres` image in the compose file |
| [Hetzner and Traefik](HETZNER-TRAEFIK.md) | Deployment | `traefik` in a compose file under `deploy/` |

A repo can use any subset. The office still works on a repo that matches no guide; its agents then rely on the repo's own `AGENTS.md`.

## The reference combination

The office was built on Django for the API, Next.js or Nuxt with Tailwind for the frontends, Postgres through Docker Compose, and Docker deploys on Hetzner behind Traefik. A repo combining them is laid out like this, with each deployable in its own directory on its own subdomain:

```
api/                 Django + DRF          → api.example.com
app/                 main web app          → app.example.com
www/                 landing pages         → www.example.com
docker-compose.yml   local Postgres + Redis
deploy/              production compose, Traefik, deploy scripts
docs/                MkDocs site: product and technical docs
docs/manual/         user manual and feature catalog, with screenshots
mkdocs.yml           the docs site
.env.example         one env file for every app
Makefile             every command an agent needs
```

with these Makefile targets:

```bash
make env       # copy .env.example to .env if missing
make install   # uv sync in api/, npm ci in each frontend
make up        # docker compose: Postgres + Redis, wait until ready
make migrate   # Django migrations
make seed      # demo data (manage.py seed_demo)
make dev       # up + migrate + seed
make test      # backend tests
make lint      # ruff
make typecheck # typecheck every frontend (builds often skip it)
make lint-fe   # eslint over every frontend
make docs      # mkdocs build --strict
make verify    # lint + test + typecheck + lint-fe + docs: the definition of done
make screenshots # seed each manual page's state and capture it at desktop and mobile widths
```

## How the office uses a guide

- **Detection.** The office checks each guide's `detect` patterns against the target's main clone. `office check` lists the stacks it found, and warns when none match.
- **Agent guidance.** Each detected guide's `## Agent guidance` section goes into every agent's prompt, under "This repo's stack". That's how a lesson learned on one Django repo reaches the agents on the next.
- **Practices review.** The PM's recurring review checks the repo against its detected stacks' guidance and suggests fixes as `Practice:` issues.
- **Readiness.** Each guide's `## Setting up a repo` section is the stack-specific half of the [integration guide](../INTEGRATION.md), for humans preparing a repo.

## Writing a guide

Create `docs/stack/<NAME>.md` (upper case, one tool per file) with this shape:

```markdown
---
name: Laravel
layer: Backend
detect: artisan, */artisan
---

# Laravel

One paragraph: what this guide covers.

## Setting up a repo

What a repo on this stack needs so agents can work on it: commands, layout,
the verify command, local development, tests.

## Agent guidance

- Short, imperative rules agents follow on this stack, each one learned the hard way.

## Deploying (optional)

---
[← Back to the stack guides](README.md)
```

- **`detect`** is a comma-separated list of globs relative to the repo root (keep them shallow, such as `*/artisan`, so detection stays fast). Add `~ text` to require that a matching file contains that text, for example `*/package.json ~ tailwindcss`.
- **Agent guidance** is pasted into every prompt, so keep it to rules an agent would otherwise get wrong. Put explanations in "Setting up a repo".
- **No project details.** Like the rest of this repo, guides use `example.com` and `owner/name`, never a real project's names or quirks.
- **Add the guide** to the table above and to the [README](../../README.md)'s Documentation table, then run `make verify`.

## Keeping guides current

When the office learns something on a target that applies to every repo on that stack, such as a command that has to run before typechecking, write it into the stack's guide in the same change. When it only applies to one repo, it belongs in that repo's own `AGENTS.md`.

---
[← Back to the README](../../README.md)
