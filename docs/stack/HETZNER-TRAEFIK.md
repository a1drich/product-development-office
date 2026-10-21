---
name: Hetzner and Traefik
layer: Deployment
detect: deploy/*.yml ~ traefik, deploy/*/*.yml ~ traefik, docker-compose*.yml ~ traefik
---

# Hetzner and Traefik

How to deploy a target repo as Docker containers on a [Hetzner Cloud](https://www.hetzner.com/cloud/) server behind [Traefik](https://doc.traefik.io/traefik/) v3, released by git tag. The server side, meaning provisioning and the shared Traefik, comes from [lobby](https://github.com/a1drich/lobby), the office's hosting companion. Several apps can share one server without depending on each other. This setup is already running in production.

## Deploying

Deploys are always a human decision. Agents never run them. This section is for setting up production once.

### Architecture

The server and each app are separate repos, and each one is deployed on its own:

| Part | Lives in | What it runs |
|---|---|---|
| Edge | [lobby](https://github.com/a1drich/lobby), checked out at `/opt/lobby` | Traefik v3: ports 80 and 443, Let's Encrypt certificates, HTTP→HTTPS redirect |
| App | The target repo's `deploy/compose.yml`, checked out at `/opt/<app>` | Postgres, Redis, a one-shot migration job, the API, workers and the frontends |

An app depends only on [lobby's contract](https://github.com/a1drich/lobby#the-contract): the external `proxy` network, the `websecure` entrypoint, the `le` certificate resolver, the `deploy` user and `/opt/<app>`. It never depends on another app on the same server, so any app can be redeployed, rolled back or removed without touching the others or dropping their TLS.

### 1. Set up the server

Follow lobby's [Set up a server](https://github.com/a1drich/lobby#set-up-a-server): create a Hetzner Cloud server running Ubuntu (2 vCPU and 4 GB holds two or three small apps), then run `lobby setup` and `lobby edge`. A server that already runs lobby skips this step.

### 2. Check the app in

Follow lobby's [Add an app](https://github.com/a1drich/lobby#add-an-app):
1. Point DNS at the server and wait until it resolves.
2. Run `lobby add-app <app> <owner/name> --release-key '<public key>'` on the server. It creates a read-only GitHub deploy key for this repo alone, the app's directories, and a release key that may only run the app's `deploy/deploy.sh`.
3. Write the app's `.env` files under `/opt/<app>`.

### 3. Route the app through Traefik

In `deploy/compose.yml`, give the project the app's name, put public services on the `proxy` network and expose them with labels. Keep Postgres and Redis on an internal network only. Lobby's [`templates/app-compose.yml`](https://github.com/a1drich/lobby/blob/main/templates/app-compose.yml) is a complete starting point.

```yaml
name: myapp

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
- **Prefix everything with the app's name:** the compose project, images, and Traefik routers, services and middlewares. **Publish no ports.** Two apps on one server can't collide that way.
- Each service follows its own stack guide: the API per [Django](DJANGO.md), the frontends per [Next.js](NEXTJS.md) or [Nuxt](NUXT.md), and the databases per [Postgres](POSTGRES.md).
- An HSTS middleware is attached to every router, and the bare domain redirects to `www` with a `redirectregex` middleware.
- Production secrets live only in `.env` files on the server, never in git.
- **The docs site can ship the same way.** `mkdocs build` produces static files, so an nginx container serving `site/` behind Traefik (for example at `docs.example.com`) publishes the manual. Like any deploy, publishing it is a human decision.

### 4. Release by git tag

Releases are `vMAJOR.MINOR.PATCH` tags on `main`, deployed by `deploy/deploy.sh` on the server:

```
make release ──► tag v1.4.0 on main ──► ssh <app>-deploy deploy v1.4.0
                 (optionally through a     └─ deploy.sh on the server:
                  GitHub Actions run           refuse tags not on main; check out the tag
                  that runs CI first)          build images tagged v1.4.0 under the server's build lock
                                               (old containers keep serving)
                                               run migrations, then recreate the services
                                               wait for health checks; keep the last 3 releases' images
```

- **The server builds the images.** No container registry is needed. Builds hold `flock /var/lock/host-docker-build.lock`, so two apps never build at once.
- **The release key is locked to one script.** `lobby add-app` adds it to `~deploy/.ssh/authorized_keys` as `command="/opt/<app>/deploy/deploy.sh",restrict`, so the key can only run that script. The script reads `deploy <tag>` or `status` from `$SSH_ORIGINAL_COMMAND`, and accepts only tags reachable from `main`.
- **Where the release runs:**
  - **Locally:** `make release` runs `ssh <app>-deploy deploy <tag>` itself, through an SSH alias on the releasing machine. This is the simplest choice when the office releases the app.
  - **Through GitHub Actions:** `deploy.yml` runs full CI on the tag, then the same `ssh`. `DEPLOY_SSH_KEY` and `DEPLOY_KNOWN_HOSTS` are GitHub Actions secrets, and `DEPLOY_HOST` (`deploy@<ip>`) is an Actions variable.
- **Make targets:**
  - `make release` tags the checked-out commit (a commit on `main`) and exits 0 only once the release is live.
  - `make rollback REF=<commit>` redeploys the release tag on that commit (`git tag --points-at <commit>`) without rebuilding.
  - `make deploy-status` shows what's running.

  With `release` and `rollback`, the office runs releases once the owner approves them (see [Releases](../WORKFLOW.md#releases)).
- **Rolling back across a schema change** needs care: see the [Django](DJANGO.md#deploying) guide.

## Agent guidance

- Never deploy, release, tag a release, roll back or change production settings, secrets or DNS, and never run `make release` or `make rollback`. Releases go out only once the owner approves them; anything else production needs is a blocker.
- Changes to `deploy/` (compose files, Traefik labels, deploy scripts) go through a normal PR, and the PR says what the owner must do on the server to apply them.
- Keep Postgres and Redis on the internal network only. Never add Traefik labels or published ports to them.
- Prefix the compose project, images, routers, services and middlewares with the app's name, and publish no ports. Only Traefik binds 80 and 443.
- The app relies only on lobby's contract. Never define Traefik or the `proxy` network in the app's repo, and never mention other apps on the server in its code or docs. Changes to Traefik itself belong in lobby.

---
[← Back to the stack guides](README.md)
