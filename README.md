# KUSANYA

**Digital Collections & Payment Infrastructure**

KUSANYA is a multi-tenant platform that lets institutions and businesses —
schools, clinics, retailers, hotels, landlords, NGOs, membership bodies,
and any other organization that bills and collects — create bills, issue
persistent control numbers, accept payments through licensed payment
providers, reconcile collections, and maintain an auditable financial
ledger. See [docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md)
for the full product vision and [docs/](docs/) for the complete
specification set.

**Status: Phase 1 — Foundation.** Identity, multi-tenancy, RBAC, and audit
logging are implemented. Billing, control numbers, payments, ledger,
reconciliation, settlement, notifications, and the external API do not
exist yet — they arrive in later phases (see
[docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md#development-phases)).
Nothing in this codebase claims to be a licensed payment institution; see
[docs/compliance/REGULATORY_ASSUMPTIONS.md](docs/compliance/REGULATORY_ASSUMPTIONS.md).

## Quick start (local, no Docker)

Prerequisites: Python 3.12+, PostgreSQL 14+, Redis 6+.

```bash
python -m venv venv
source venv/Scripts/activate        # Windows Git Bash; use venv\Scripts\activate.bat on cmd
pip install -r requirements/development.txt

cp .env.example .env                # then edit DATABASE_URL / REDIS_URL to match your setup

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit http://127.0.0.1:8000/ — anonymous visitors land on sign-in;
`/register/` starts the institution-onboarding journey; `/admin/` is the
Django admin for platform staff.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL, Redis, the Django app, a Celery worker, and Celery
beat. The web app listens on `http://localhost:8000/`. Host ports for
Postgres/Redis are non-default (`5434`/`6381`) to avoid clashing with other
local services — see the comment at the top of
[docker-compose.yml](docker-compose.yml).

## Running tests

```bash
python -m pytest
```

Tests run against `config.settings.testing` (see
[pytest.ini](pytest.ini)), which points at the same PostgreSQL instance
`DATABASE_URL` resolves to but uses a disposable `test_<db>` database that
Django creates and tears down automatically.

## Project layout

```
apps/            Django apps, one per domain (see docs/DATABASE_ARCHITECTURE.md)
config/          Django project: settings/, urls.py, celery.py, wsgi.py, asgi.py
templates/       Server-rendered UI (Bootstrap 5 + HTMX, no React/Next.js)
static/          CSS/JS
docs/            Full specification and architecture documentation
docker-compose.yml, Dockerfile, requirements/
```

## Documentation

Start with [docs/README.md](docs/README.md) for an index of every
specification document, or [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)
for the reasoning behind foundational choices.
