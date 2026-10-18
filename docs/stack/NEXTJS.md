---
name: Next.js
layer: Frontend
detect: next.config.*, */next.config.*
---

# Next.js

How the office works with [Next.js](https://nextjs.org/) frontends written in [TypeScript](https://www.typescriptlang.org/): what the repo needs, and the rules agents follow on it. Styling is covered in [Tailwind CSS](TAILWIND.md).

## Setting up a repo

- **Dependencies are installed explicitly.** A fresh clone runs `npm ci` before anything else. The verify script should stop early with a clear message pointing at `npm ci` when `node_modules` is missing, instead of failing on `tsc: command not found`.
- **Typecheck explicitly, with generated types first.** Production builds don't prove the types are right, so verify runs a typecheck. Next.js generates route types (such as `LayoutProps` and `PageProps`) into `.next/types`, so a typecheck on a fresh clone fails until they exist. Make each app's `typecheck` script `next typegen && tsc --noEmit`.
- **Ports are configurable.** Each app's dev server has a default port in its `dev` script (`next dev -p 3001`), and every URL another app or the API needs (`NEXT_PUBLIC_*`, `API_BASE_URL`) comes from the environment, so an app can run on any free port.
- **Each app reads its settings from `.env.local`,** with a `.env.example` listing every variable and working as-is. Variables set in the process environment override `.env.local`.
- **Several apps in one repo** use npm workspaces, with shared code in `packages/*`. Apps on separate origins link to each other with full URLs from the environment, never relative links.
- **End-to-end tests** run with [Playwright](https://playwright.dev/) against their own dev servers, on ports and a database derived from the checkout (with env overrides), so two checkouts can run them at once.

## Agent guidance

- Run `npm ci` in a fresh worktree before any frontend command, and again after `package-lock.json` changes.
- Typecheck with the app's `typecheck` script (which runs `next typegen` first), not with `next build` alone. A build that passes can still have type errors.
- When you start dev servers for testing, use free ports (`next dev -p <port>`) and point the cross-app URLs at them through environment variables. Never stop servers you didn't start.
- `NEXT_PUBLIC_*` variables are inlined at build time. After changing one, restart the dev server or rebuild before checking the result.
- Prefer Server Components. Add `"use client"` only to components that need state, effects or browser APIs.
- Third-party widgets that render their own text (such as a Google sign-in button) pick a language from the visitor unless told otherwise. Pass the product's locale explicitly.

## Deploying

- Build each app into a container. Public build-time variables (`NEXT_PUBLIC_*`) are baked into the image, so changing one needs a rebuild.
- See [Hetzner and Traefik](HETZNER-TRAEFIK.md) for the rest of the deploy setup.

---
[← Back to the stack guides](README.md)
