---
name: Postgres
layer: Data
detect: docker-compose.yml ~ postgres, docker-compose.yaml ~ postgres, compose.yml ~ postgres, compose.yaml ~ postgres
---

# Postgres

How the office works with a [Postgres](https://www.postgresql.org/) database run locally through [Docker Compose](https://docs.docker.com/compose/) (with [Redis](https://redis.io/) alongside when needed): what the repo needs, how the office cleans up after its agents, and the rules agents follow.

## Setting up a repo

- **A compose file starts the database.** `docker-compose.yml` at the repo root runs a `postgres` image with its credentials in `environment` (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) and port 5432 published to the host. Add Redis there if the app needs it.
- **Every database name is overridable from the environment:** the dev database (`DATABASE_URL`), the test database and any end-to-end database. Agents name the databases they create with a prefix the office gives them, and only databases named that way get cleaned up.
- **Defaults are per checkout.** When no override is set, test and end-to-end databases get names derived from the checkout's path, so parallel worktrees sharing one Postgres server never collide.
- **A separate database per branch is documented.** A branch with new migrations can't share the dev database with branches that don't have them, so the repo's docs explain how to point `DATABASE_URL` at a throwaway database.

## How the office cleans up

The office reads the Postgres service from the target's compose config (the service whose image starts with `postgres`, its published port and credentials) and connects from the host. After every engineer, reviewer or tester run, it drops each database named with that issue's prefix (`office_<repo hash>_i<N>_`). It never touches a name outside `office_`. A repo whose Postgres isn't in a compose file, or isn't published to the host, gets no cleanup. See [Architecture](../ARCHITECTURE.md) for the details.

## Agent guidance

- Name every database you create with your database prefix, through the repo's overrides (dev, test and end-to-end). The office drops them when your run ends.
- Never drop, migrate, reseed or write test data into a database you didn't create, the shared dev database included.
- Start Postgres with `docker compose up -d postgres` only if it isn't already running. Other checkouts share the same server, so never stop it or remove its volume.

## Deploying

In production, Postgres and Redis run on an internal Docker network only, never exposed to the internet. See [Hetzner and Traefik](HETZNER-TRAEFIK.md).

---
[← Back to the stack guides](README.md)
