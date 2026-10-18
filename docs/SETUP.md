# Setup guide

This guide covers three things:

1. [Setting up the machine that runs the office](#1-the-office-machine)
2. [Preparing a target repo](#2-preparing-a-target-repo) so the agents can work on it
3. [Deploying a target repo](#3-deploying-to-hetzner-behind-traefik) to Hetzner behind Traefik

The target-repo and deployment sections describe a setup that is already running in production.

---

## 1. The office machine

The office runs as a long-running process on a local machine.

### Install

| Tool | Why |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Runs the orchestrator, and installs Python 3.12+ for it |
| [GitHub CLI](https://cli.github.com/) (`gh`) | All issue, label and PR work |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | PM, Designer and Engineers |
| [Codex CLI](https://github.com/openai/codex) | Reviewers and Testers |
| [Docker](https://docs.docker.com/get-docker/) | Postgres and Redis for each target repo's tests |
| [Node.js](https://nodejs.org/) 24 + npm | Target repo frontends |

### Log in, with subscriptions only

```bash
gh auth login                                  # needs write access to the target repo
gh auth refresh -h github.com -s workflow      # only if agents should edit .github/workflows/

claude                                         # then /login with a Claude subscription
codex login                                    # choose "Sign in with ChatGPT"
```

Make sure no API keys are set in your shell. The office refuses to start if one is set:

```bash
unset ANTHROPIC_API_KEY OPENAI_API_KEY ANTHROPIC_AUTH_TOKEN
```

### Install and start

```bash
git clone https://github.com/a1drich/product-development-office
cd product-development-office
uv sync
uv run playwright install chromium           # once, for UI screenshots

uv run office check acme/widget-app          # is the repo ready?
uv run office start acme/widget-app --dry-run
uv run office start acme/widget-app          # or just `office start` to be asked
```

For an existing repo, work through the [integration guide](INTEGRATION.md) first.

---

## 2. Preparing a target repo

The agents work best on a repo that follows the conventions below. A repo that already looks like this needs no extra setup.

### Stack

| Layer | Tools |
|---|---|
| Backend | [Django](https://www.djangoproject.com/) + [Django REST Framework](https://www.django-rest-framework.org/), [uv](https://docs.astral.sh/uv/), [ruff](https://docs.astral.sh/ruff/), [pytest-django](https://pytest-django.readthedocs.io/) |
| Background jobs | [Celery](https://docs.celeryq.dev/) on [Redis](https://redis.io/), if needed |
| Frontends | [Nuxt](https://nuxt.com/) or [Next.js](https://nextjs.org/), TypeScript, [Tailwind CSS](https://tailwindcss.com/) v4 |
| Data | [Postgres](https://www.postgresql.org/) via [Docker Compose](https://docs.docker.com/compose/) |
| Docs | [MkDocs](https://www.mkdocs.org/) with [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/): docs site, user manual and feature catalog |
| UI testing | [Playwright](https://playwright.dev/), through `office shoot` |
| Deploy | [Hetzner Cloud](https://www.hetzner.com/cloud/), [Traefik](https://doc.traefik.io/traefik/) v3, GitHub Actions |

### Layout

Each deployable has its own directory and its own subdomain:

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

### Docs site and user manual

`docs/` is an [MkDocs](https://www.mkdocs.org/) site (`mkdocs.yml`, Material theme), and it is delivered with every change:

- `docs/manual/README.md` is the user manual and feature catalog: one section per feature or page, with desktop and mobile screenshots from `docs/manual/screenshots/`. The owner reviews the product through it.
- `docs/manual/pages.json` lists the pages to screenshot. `make screenshots` captures them, with each page's state set up. `office shoot` is the fallback for repos without that command.
- `uvx --with mkdocs-material mkdocs build --strict` must pass. Add it to `make verify` so broken links and pages missing from the nav fail the build.
- While the office runs, the site is served live at `http://127.0.0.1:8787` from the target's main clone, and refreshed after every merge. `office docs serve owner/name` serves it on its own.

The [integration guide](INTEGRATION.md#add-the-docs-site-and-user-manual) has starter files.

### Files the agents read

| File | Purpose |
|---|---|
| `AGENTS.md` | Commands, architecture, conventions and rules, such as when to file a blocker and what never to touch. Every agent reads it first. |
| `CLAUDE.md` | Just `@AGENTS.md`, so Claude Code reads the same file as Codex |
| `mkdocs.yml`, `docs/manual/` | The docs site and user manual. Every role keeps it current. |
| `PRODUCT.md`, `DESIGN.md` or `docs/design-system.md` | Who the users are and the visual system. The Designer works from and updates these. |
| `docs/` | Strategy, specs, data model, decision log. Agents follow decisions written here instead of "fixing" them. |
| `docs/BACKLOG.md` (optional) | An index of what's done, what agents can build now and what's blocked |
| `docs/OWNER-TODO.md` (optional) | Things only a human can do (accounts, money, legal, DNS) |

### Makefile targets

Agents rely on these targets. The names match the reference setup:

```bash
make env       # copy .env.example to .env if missing
make install   # uv sync in api/, npm install in each frontend
make up        # docker compose: Postgres + Redis, wait until ready
make migrate   # Django migrations
make seed      # demo data (manage.py seed_demo)
make dev       # up + migrate + seed
make test      # backend tests
make lint      # ruff
make typecheck # tsc / vue-tsc over every frontend (frontend builds often skip type checking)
make lint-fe   # eslint over every frontend
make docs      # mkdocs build --strict
make verify    # lint + test + typecheck + lint-fe + docs: the definition of done
make ui-check  # optional: headless smoke test of the running app at phone width
```

`make verify` is the gate. Engineers run it before opening a PR. Testers run it again on the PR branch before merging.

### Local development must work offline

- **Mock every external service** behind an env flag (for example `META_MOCK=true`, `BILLING_MOCK=true`), so the full product runs end to end with no third-party accounts or internet.
- **Tests use their own database**, separate from the dev database. This lets parallel agents run test suites without clobbering each other.
- **Insecure dev defaults are fine** as long as settings refuse to boot with them when `DJANGO_DEBUG=false`.

### GitHub

- Turn on Issues. The office creates its labels on first run.
- Commit the [impeccable](https://github.com/pbakaus/impeccable) design skill (`npx skills add pbakaus/impeccable`), so every agent's fresh clone has it. If you don't, `office start` files it as the office's first task.
- Add CI (`.github/workflows/ci.yml`) that runs the same checks as `make verify` on pull requests. The tester waits for it before merging.
- Protect `main` from force-pushes. Agents merge PRs, but only through `gh pr merge`.

---

## 3. Deploying to Hetzner behind Traefik

Deploys are always a human decision. Agents never run them. This section is for setting up production once.

### Architecture

One Hetzner server runs Docker with two compose stacks:

| Stack | File | What it runs |
|---|---|---|
| Edge | `deploy/traefik/compose.yml` | Traefik v3: ports 80 and 443, Let's Encrypt certificates, HTTP→HTTPS redirect |
| App | `deploy/compose.yml` | Postgres, Redis, a one-shot migration job, the API, workers and the frontends |

Traefik runs as its own stack. That way an app can be redeployed without dropping TLS for anything else on the host, and more apps can share the same server.

### 1. Create the server

1. Create a [Hetzner Cloud](https://console.hetzner.cloud/) server running Ubuntu. 2 vCPU and 4 GB of memory is enough for a small product. Add your SSH key.
2. Add DNS A records for `@`, `www`, `app` and `api` pointing at the server IP. DNS must resolve before Traefik starts, or the first certificate request fails.
3. Run a one-time setup script as root. It should:
   - install Docker, Compose and buildx
   - set up a firewall (`ufw`) allowing only SSH, 80 and 443
   - add 2 GB of swap, so image builds don't crash the running site when memory spikes
   - create a `deploy` user in the `docker` group
   - generate a read-only GitHub deploy key for that user
   - create the shared Docker network: `docker network create proxy`

### 2. Start Traefik

```yaml
# deploy/traefik/compose.yml
services:
  traefik:
    image: traefik:v3.6  # 3.6 or later: older releases can't talk to Docker 29
    container_name: traefik
    restart: unless-stopped
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --providers.docker.network=proxy
      - --entrypoints.web.address=:80
      - --entrypoints.web.http.redirections.entrypoint.to=websecure
      - --entrypoints.web.http.redirections.entrypoint.scheme=https
      - --entrypoints.websecure.address=:443
      - --entrypoints.websecure.http.tls.certresolver=le
      - --certificatesresolvers.le.acme.email=${ACME_EMAIL:-}
      - --certificatesresolvers.le.acme.storage=/letsencrypt/acme.json
      - --certificatesresolvers.le.acme.tlschallenge=true
    ports: ["80:80", "443:443"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - letsencrypt:/letsencrypt
    networks: [proxy]

networks:
  proxy:
    external: true

volumes:
  letsencrypt:
```

```bash
cd deploy/traefik && docker compose up -d
```

### 3. Route the app through Traefik

In `deploy/compose.yml`, put public services on the `proxy` network and expose them with labels. Keep Postgres and Redis on an internal network only.

```yaml
services:
  api:
    image: myapp-api:${APP_TAG:-dev}
    build: ../api
    networks: [internal, proxy]
    labels:
      - traefik.enable=true
      - traefik.http.routers.myapp-api.rule=Host(`api.example.com`)
      - traefik.http.routers.myapp-api.entrypoints=websecure
      - traefik.http.services.myapp-api.loadbalancer.server.port=8000

networks:
  internal:
  proxy:
    external: true
```

Patterns that work well:
- The API runs on gunicorn, with static files served by whitenoise.
- Frontends are static builds served by nginx, so the only long-running Python processes are the API and the workers. Public build-time variables (such as `NUXT_PUBLIC_*` or `NEXT_PUBLIC_*`) are baked into the image, so changing one needs a rebuild.
- An HSTS middleware is attached to every router, and the bare domain redirects to `www` with a `redirectregex` middleware.
- Production secrets live only in `.env` files on the server, never in git.
- **The docs site can ship the same way.** `mkdocs build` produces static files, so an nginx container serving `site/` behind Traefik (for example at `docs.example.com`) publishes the manual. Like any deploy, publishing it is a human decision.

### 4. Release by git tag

Releases are `vMAJOR.MINOR.PATCH` tags on `main`:

```
pull request ──► ci.yml: ruff, tests, typecheck, eslint
tag v*.*.*   ──► deploy.yml: full CI ──► ssh deploy@server "deploy v1.4.0"
                                          └─ deploy.sh on the server:
                                             refuse tags not on main; check out the tag
                                             build images tagged v1.4.0 (old containers keep serving)
                                             run migrations, then recreate the services
                                             wait for health checks; keep the last 3 releases' images
```

- **The server builds the images.** No container registry is needed.
- **The GitHub Actions SSH key is locked to one script.** Its entry in `~deploy/.ssh/authorized_keys` uses `command="/opt/<app>/deploy/deploy.sh",restrict`, so the key can only run that script. It accepts only tags reachable from `main`.
- **Secrets:** `DEPLOY_SSH_KEY` and `DEPLOY_KNOWN_HOSTS` are GitHub Actions secrets, and `DEPLOY_HOST` (`deploy@<ip>`) is an Actions variable.
- **Make targets:** `make release` tags `origin/main` and follows the Actions run. `make rollback V=v1.3.2` redeploys an older tag without rebuilding. `make deploy-status` shows what's running.
- **Migrations don't run backwards.** Before rolling back across a release that changed the schema, check `git diff vOLD vNEW -- '*/migrations/*'`. If it isn't empty, fix forward instead.
