---
name: Hetzner and Traefik
layer: Deployment
detect: deploy/*.yml ~ traefik, deploy/*/*.yml ~ traefik, docker-compose*.yml ~ traefik
---

# Hetzner and Traefik

How to deploy a target repo as Docker containers on a [Hetzner Cloud](https://www.hetzner.com/cloud/) server behind [Traefik](https://doc.traefik.io/traefik/) v3, released by git tag through GitHub Actions. This setup is already running in production.

## Deploying

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
- Each service follows its own stack guide: the API per [Django](DJANGO.md), the frontends per [Next.js](NEXTJS.md) or [Nuxt](NUXT.md), and the databases per [Postgres](POSTGRES.md).
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
- **Make targets:** `make release` tags the checked-out commit (a commit on `main`) and follows the Actions run. `make rollback REF=<commit>` redeploys the release tag on that commit (`git tag --points-at <commit>`) without rebuilding. `make deploy-status` shows what's running. With `release` and `rollback`, the office runs releases once the owner approves them (see [Releases](../WORKFLOW.md#releases)).
- **Rolling back across a schema change** needs care: see the [Django](DJANGO.md#deploying) guide.

## Agent guidance

- Never deploy, release, tag a release, roll back or change production settings, secrets or DNS, and never run `make release` or `make rollback`. Releases go out only once the owner approves them; anything else production needs is a blocker.
- Changes to `deploy/` (compose files, Traefik labels, deploy scripts) go through a normal PR, and the PR says what the owner must do on the server to apply them.
- Keep Postgres and Redis on the internal network only. Never add Traefik labels or published ports to them.

---
[← Back to the stack guides](README.md)
