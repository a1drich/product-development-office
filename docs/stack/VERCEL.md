---
name: Vercel
layer: Deployment
detect: vercel.json, */vercel.json
---

# Vercel

How to host a target repo on [Vercel](https://vercel.com/) through its Git integration, so that merges to `main` never deploy production on their own. Vercel suits static sites and frontends, such as a [Vite](VITE.md) single-page app.

## Setting up a repo

- **Commit a `vercel.json`,** even when Vercel's framework detection needs none, because it's how the office detects this guide. A single-page app needs one anyway, for its rewrite to `index.html`: `{"rewrites": [{"source": "/(.*)", "destination": "/index.html"}]}`.
- **The preview build is a PR check.** Vercel builds a preview deployment for every PR and reports it as a check, which the Tester requires to pass before merging, like any CI. Keep the Vercel build command the same as the one verify runs, so a PR that passes verify also passes the preview build.
- **Environment variables live in the Vercel project,** never in git. `.env.example` lists every variable, and the project settings hold the real values for each environment.
- **Don't commit `.vercel/`.** `vercel link` writes it locally, and it belongs in `.gitignore`.

## Deploying

Deploys are always a human decision, and a merge never triggers one. Out of the box, Vercel deploys production on every push to the production branch, which is `main`, so a repo the office works on changes that once:

1. Create a `production` branch from `main`: `git push origin main:production`.
2. In the Vercel project, open **Settings → Environments → Production**, set **Branch Tracking** to `production` and save.

Merges to `main` then build preview deployments only. To release, the owner fast-forwards `production` to the commit they want live, for example `git push origin main:production`. To roll back, they promote an earlier production deployment in Vercel's dashboard, or reset `production` to an earlier commit.

The custom domain is set in the project's **Settings → Domains**, and pointed at Vercel at the DNS provider. That, too, is done by the owner.

## Agent guidance

- Never deploy, promote, roll back or change production settings, environment variables, domains or DNS. Never push to the `production` branch, and never run `vercel deploy`, `vercel --prod`, `vercel promote`, `vercel rollback` or `vercel env`. Those are always a human decision; file a blocker instead.
- Changes to `vercel.json` (rewrites, redirects, headers) go through a normal PR, and the PR says what they change on the live site once released.
- A failing Vercel preview check blocks the merge like any CI failure. Read its build log (the check links to it) and reproduce it locally with the repo's build command.

---
[← Back to the stack guides](README.md)
