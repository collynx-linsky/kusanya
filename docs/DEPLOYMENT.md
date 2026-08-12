# Deployment

## Environments

Four `DJANGO_SETTINGS_MODULE` targets: `config.settings.development`,
`.testing`, `.staging` (not yet created as a distinct file — currently
staging should use `.production` with environment-specific env vars until
staging-specific behavior is actually needed), `.production`. See
`config/settings/` and [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md)
ADR-007 for why they're split rather than one file with `if DEBUG`
branches.

## Local development

Two supported paths, both documented in [../README.md](../README.md):
plain `venv` + a locally reachable PostgreSQL/Redis, or full
`docker compose up`. Phase 1 was built and verified using a hybrid: the
`db`/`redis` services from `docker-compose.yml` (via `docker compose up -d
db redis`), with Django/Celery run natively from the `venv` against those
containers — fastest edit-test loop while still testing against real
PostgreSQL/Redis rather than SQLite/in-memory fakes.

## Docker services

`docker-compose.yml`: `db` (postgres:16-alpine), `redis` (redis:7-alpine),
`web` (Django dev server), `celery_worker`, `celery_beat`
(django-celery-beat `DatabaseScheduler`). No `nginx` service in the dev
compose file — the Django dev server serves directly on `:8000` for
local work; production fronts the app with a reverse proxy (see below).
Host ports are non-default (`5434` for Postgres, `6381` for Redis) to
avoid colliding with this developer's other locally running projects —
see the comment at the top of `docker-compose.yml`; inside the Docker
network, services use the standard `5432`/`6379`.

## Production topology (target, not yet deployed)

```
Internet → reverse proxy / load balancer (TLS termination) → gunicorn (config.wsgi)
                                                             → celery worker(s)
                                                             → celery beat
                                                             ↓
                                                          PostgreSQL (managed)
                                                          Redis (managed)
```

`config/settings/production.py` assumes: `SECURE_PROXY_SSL_HEADER` is
trustworthy because a proxy that strips/sets `X-Forwarded-Proto` sits in
front of the app (never expose gunicorn directly to the internet);
`DJANGO_SECRET_KEY`/`DJANGO_ALLOWED_HOSTS` are provided by the deployment
environment, not defaulted. `whitenoise` serves static files directly
from the Django process (`STORAGES["staticfiles"]` uses
`CompressedManifestStaticFilesStorage`) — acceptable at Phase 1/early
scale; revisit with a CDN/object storage once static asset volume or
global latency requirements justify it. Vendor Bootstrap/HTMX locally
(currently CDN-loaded in `templates/base.html`) before production so the
app has no runtime dependency on a third-party CDN's availability.

## What's not decided yet

Actual hosting provider, managed Postgres/Redis choice, CI/CD pipeline,
container registry, and secrets manager are all deployment decisions not
made by this Phase 1 build — they depend on infrastructure choices
outside this codebase's scope.
