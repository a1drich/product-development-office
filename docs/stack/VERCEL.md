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

Merges to `main` then build preview deployments only. A release is moving `production` to a commit on `main`, so give the repo release and rollback commands that do just that:

```makefile
release:   # put the checked-out commit live
	git push origin HEAD:refs/heads/production

rollback:  # put an earlier commit back: make rollback REF=<commit>
	@test -n "$(REF)" || { echo "usage: make rollback REF=<commit>"; exit 1; }
	git push --force origin $(REF):refs/heads/production
```

Keep the `REF` check: without it, an empty `REF` pushes `:refs/heads/production`, which deletes the branch. With these, the office releases once the owner approves (see [Releases](../WORKFLOW.md#releases)), running `make release` in a checkout of the approved commit. Without them, the owner runs `git push origin main:production` by hand, and rolls back by promoting an earlier production deployment in Vercel's dashboard. Vercel builds each push to `production` before it goes live, so give the live check a minute or two.

The custom domain is set in the project's **Settings → Domains**, and pointed at Vercel at the DNS provider. That, too, is done by the owner.

## Agent guidance

- Never deploy, promote, roll back or change production settings, environment variables, domains or DNS. Never push to the `production` branch, never run `make release` or `make rollback`, and never run `vercel deploy`, `vercel --prod`, `vercel promote`, `vercel rollback` or `vercel env`. Releases go out only once the owner approves them; anything else production needs is a blocker.
- Changes to `vercel.json` (rewrites, redirects, headers) go through a normal PR, and the PR says what they change on the live site once released.
- A failing Vercel preview check blocks the merge like any CI failure. Read its build log (the check links to it) and reproduce it locally with the repo's build command.

---
[← Back to the stack guides](README.md)
