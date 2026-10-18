---
name: Django
layer: Backend
detect: manage.py, */manage.py
---

# Django

How the office works with a [Django](https://www.djangoproject.com/) + [Django REST Framework](https://www.django-rest-framework.org/) backend managed with [uv](https://docs.astral.sh/uv/) and linted with [ruff](https://docs.astral.sh/ruff/): what the repo needs, and the rules agents follow on it.

## Setting up a repo

- **Layout.** The API lives in its own directory (`api/` or `backend/`) with its own `pyproject.toml`, run with `uv run`. Background jobs, if any, use [Celery](https://docs.celeryq.dev/) on Redis.
- **Commands.** The repo's verify command runs `ruff check`, `ruff format --check`, `manage.py check`, `makemigrations --check --dry-run` and the full test suite (`manage.py test` or [pytest-django](https://pytest-django.readthedocs.io/)). Typical Makefile targets: `migrate`, `seed` (`manage.py seed_demo`), `test`, `lint`.
- **Settings from the environment** (for example with `django-environ`). `DEBUG` defaults to `False` in `settings.py`, and `.env.example` sets the local values, `DEBUG=True` included, so `cp .env.example .env` is all a fresh clone needs. Insecure dev defaults are fine as long as settings refuse to boot with them when `DEBUG` is off.
- **Tests get their own database, one per checkout.** Set `DATABASES['default']['TEST']['NAME']` from an env var (for example `TEST_DB_NAME`, used verbatim), defaulting to a name derived from the checkout's path, such as `test_<project>_<8-char hash>`. Parallel worktrees then never share a test database, and agents can name theirs with the office's prefix.
- **The dev database name is overridable too** (`DATABASE_URL`), so a branch with new migrations can use its own database instead of migrating the shared one.
- **Migrations are checked in verify.** `makemigrations --check --dry-run` fails the build when a model change has no migration.
- **Demo data.** A `seed_demo` management command creates a realistic dataset and prints ready-to-use test accounts. It resets its own data, so it is safe to re-run.
- **OAuth-only sign-in needs a local shortcut.** If users can only sign in with a third party such as Google, add a dev-only sign-in endpoint that is active only when `DEBUG` is on, so testers can sign in as seeded accounts without real credentials.

## Agent guidance

- Run the backend tests against a database named with your database prefix, through the repo's test-database override (for example `TEST_DB_NAME=<prefix>test`). Never rely on the default name, which other checkouts may share.
- Never reseed or migrate the shared dev database for your work. Create your own with the prefix (`DATABASE_URL=postgres://…/<prefix>dev`), migrate it and run `seed_demo` there.
- After changing a model, run `makemigrations`, commit the migration with the change, and check that `makemigrations --check --dry-run` passes.
- After merging the base branch, run `showmigrations` or `migrate` on a fresh database. Two leaf migrations in one app is a conflict: engineers add a merge migration (`makemigrations --merge`) to the PR, and testers fail a PR that still has two leaves after merging the base branch.
- Never edit a migration that has already merged, and never depend on migrations running backwards. Fix forward with a new migration.
- In multi-tenant apps, scope every queryset to the requesting user's tenant (business, organization or account). Reviewers treat an unscoped queryset in a view or serializer as a blocking finding.
- Run `manage.py check` after any change to settings or URLs, and `ruff format` before committing.

## Deploying

- The API runs on gunicorn, with static files served by whitenoise.
- Migrations run as a one-shot job before the API is recreated. Before rolling back across a release that changed the schema, check `git diff vOLD vNEW -- '*/migrations/*'`. If it isn't empty, fix forward instead.
- See [Hetzner and Traefik](HETZNER-TRAEFIK.md) for the rest of the deploy setup.

---
[← Back to the stack guides](README.md)
