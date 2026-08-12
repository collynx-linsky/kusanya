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

**Status: all six build phases complete.** Identity, multi-tenancy, RBAC,
audit logging, customers/accounts, billing, the persistent control-number
engine, the payment domain (full lifecycle, UNKNOWN-on-timeout handling,
idempotent initiation and callbacks), a mock/sandbox provider adapter,
signed outbound webhook delivery, an immutable financial ledger, the
revenue engine (the TZS 50 control-number/payment fees are genuinely
charged, exactly once each — the build spec's own worked example, one
control number + five payments = TZS 300, is reproduced exactly),
reconciliation, settlement batching (with database-enforced
double-settlement prevention), templated multi-channel notifications
(real email, MOCK/SANDBOX SMS), automatically generated receipts, a
focused reporting layer, and a full external REST API with credential
authentication, rate limiting, and two layers of idempotency are all
implemented and tested against real PostgreSQL — 149 automated tests,
plus extensive manual end-to-end verification, including a real
`curl`-driven customer→account→bill→control-number→payment sequence run
entirely through the external API against the live server. Nothing in
this codebase claims to be a licensed payment institution; see
[docs/compliance/REGULATORY_ASSUMPTIONS.md](docs/compliance/REGULATORY_ASSUMPTIONS.md).
What's genuinely not built — a second (real) payment provider, production
hardening, and more — is documented honestly per-domain rather than
implied to exist; see each doc's "what's not built" section and
[docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md).

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
Django admin for platform staff; `/api/docs/` is the interactive API
documentation (Swagger UI) once you've created an API credential from
the tenant portal's Developers menu.

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

## Domains implemented

`core` · `users` · `accounts` · `tenants` · `organizations` · `audit` ·
`customers` · `billing` · `control_numbers` · `providers` · `payments` ·
`webhooks` · `ledger` · `revenue` · `reconciliation` · `settlement` ·
`notifications` · `receipts` · `reports` · `api`

## Documentation

Start with [docs/README.md](docs/README.md) for an index of every
specification document, or [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)
for the reasoning behind foundational choices (24 ADRs as of Phase 6).
