---
name: Vite
layer: Frontend
detect: vite.config.*, */vite.config.*
---

# Vite

How the office works with single-page apps built with [Vite](https://vite.dev/), usually in React: what the repo needs, and the rules agents follow on it. This covers static sites such as a marketing site, where `vite build` produces a `dist/` folder that a host serves as-is. Styling is covered in [Tailwind CSS](TAILWIND.md), and hosting on Vercel in [Vercel](VERCEL.md).

## Setting up a repo

- **Dependencies are installed explicitly.** A fresh clone runs `npm ci` before anything else. The verify script should stop early with a clear message pointing at `npm ci` when `node_modules` is missing.
- **`npm run verify` is the definition of done.** Vite's build doesn't lint or typecheck, so verify runs each check itself and exits non-zero on any failure. For a JavaScript site that's `eslint .`, the Tailwind token check, `vite build`, the end-to-end smoke test and `mkdocs build --strict`. A TypeScript site adds `tsc --noEmit` (or `tsc -b`) before the build.
- **Ports are configurable.** The `dev` and `preview` scripts take `--port`, and the repo doesn't hard-code a port in `vite.config.*`. Without `--strictPort`, Vite silently moves to the next free port when the one it asked for is busy.
- **Settings come from `.env` files.** Vite exposes only variables prefixed `VITE_` to the browser, and inlines them into the bundle at build time. `.env.example` lists every variable and works as-is. A site with no variables still commits a `.env.example` that says so.
- **Every route has its own title and description.** A single-page app ships one `index.html`, so a route that doesn't set `document.title` and its meta description shows the home page's to visitors and search engines. Set them per route (React 19 renders `<title>` and `<meta>` from inside components), or prerender the routes.
- **The host rewrites unknown paths to `index.html`,** so a deep link such as `/about` loads the app instead of a 404. `vite dev` and `vite preview` do this already, so check deep links against the host's config, not just locally.
- **An end-to-end smoke test** with [Playwright](https://playwright.dev/) opens every route against `vite preview` on a port from the environment, and checks it renders without console errors. `docs/manual/pages.json` lists the same routes, so `office shoot` can screenshot a static site without a `make screenshots` target.

## Agent guidance

- Run `npm ci` in a fresh worktree before any frontend command, and again after `package-lock.json` changes.
- Start dev and preview servers only on your leased ports, with `--strictPort` (`npm run dev -- --port <port> --strictPort`), so Vite fails instead of moving to a port you don't hold.
- Check changes against the production build (`npm run build`, then `npm run preview -- --port <port> --strictPort`), not just the dev server. Asset paths, environment variables and code splitting can differ between them.
- Only `VITE_*` variables reach the browser, and they are inlined into the bundle, so they are public. Never put a secret in one. After changing one, restart the server or rebuild.
- When you add a route, add it to the router, the smoke test and `docs/manual/pages.json`, and give it its own title and meta description.
- Files in `public/` are served from the site root and referenced by absolute path (`/logo.svg`). Import assets that live in `src/` so the build fingerprints them.

---
[← Back to the stack guides](README.md)
