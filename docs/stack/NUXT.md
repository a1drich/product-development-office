---
name: Nuxt
layer: Frontend
detect: nuxt.config.*, */nuxt.config.*
---

# Nuxt

How the office works with [Nuxt](https://nuxt.com/) frontends written in [TypeScript](https://www.typescriptlang.org/): what the repo needs, and the rules agents follow on it. Styling is covered in [Tailwind CSS](TAILWIND.md).

## Setting up a repo

- **Dependencies are installed explicitly.** A fresh clone runs `npm ci` before anything else, and the verify script stops early with a clear message when `node_modules` is missing.
- **Typecheck explicitly.** Production builds don't type-check, so verify runs `nuxi typecheck` (or `vue-tsc --noEmit`) for each app. Nuxt generates its types into `.nuxt/`, so run `nuxi prepare` first on a fresh clone.
- **Ports are configurable.** Each app's dev server port and every URL it needs (`NUXT_PUBLIC_*`) come from the environment, so an app can run on any free port.
- **A `.env.example`** lists every variable and works as-is for local development.

## Agent guidance

- Run `npm ci` in a fresh worktree before any frontend command, and again after `package-lock.json` changes.
- Typecheck with `nuxi typecheck` (after `nuxi prepare` on a fresh checkout), not with `nuxi build` alone.
- When you start dev servers for testing, use free ports (`nuxi dev --port <port>`) and point the app's URLs at them through environment variables. Never stop servers you didn't start.
- Public runtime config (`NUXT_PUBLIC_*`) is baked into static builds. After changing one, rebuild before checking the result.

## Deploying

- Frontends are static builds (`nuxi generate`) served by nginx, so the only long-running processes are the API and its workers. Public variables (`NUXT_PUBLIC_*`) are baked into the image, so changing one needs a rebuild.
- See [Hetzner and Traefik](HETZNER-TRAEFIK.md) for the rest of the deploy setup.

---
[← Back to the stack guides](README.md)
