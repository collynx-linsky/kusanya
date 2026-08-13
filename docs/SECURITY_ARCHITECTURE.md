# Security Architecture

Treat this platform as financial infrastructure at every layer (build
spec section 28). This document lists what's actually implemented, what's
configured-but-not-yet-exercised, and what's explicitly not done —
overstating any of these would be its own security problem.

## Implemented (Phase 1)

- **Authentication:** Django's session-based auth, custom email-only
  `User` model (`apps.users.models.User`), password hashing via Django's
  default (PBKDF2) hasher, minimum password length 12
  (`AUTH_PASSWORD_VALIDATORS` in `config/settings/base.py`).
- **Authorization:** server-enforced RBAC — see [RBAC.md](RBAC.md).
- **Tenant isolation:** see [MULTI_TENANCY.md](MULTI_TENANCY.md).
- **CSRF protection:** Django's default middleware, enabled everywhere;
  all state-changing forms (login, logout, onboarding, tenant approval)
  use POST + `{% csrf_token %}`.
- **Session cookies:** `HttpOnly` always; `Secure` in production
  (`config/settings/production.py`), relaxed only in `development.py` for
  local plain-HTTP testing.
- **Audit logging:** hash-chained, immutable at the model layer
  (`apps.audit.models.AuditLog`) — see
  [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-006 for
  the honest limits of what this chain does and does not guarantee.
- **SQL injection:** exclusively via Django ORM / parameterized queries;
  no raw SQL string interpolation anywhere in the codebase.
- **XSS:** Django template auto-escaping is on everywhere; no
  `|safe`/`mark_safe` usage in Phase 1 templates.
- **Structured, correlated logging:** every request gets a correlation ID
  (`apps.core.middleware.CorrelationIdMiddleware`), included in every log
  line via `apps.core.logging.CorrelationIdFilter` and echoed back as an
  `X-Correlation-ID` response header.
- **Consistent error envelope:** `apps.core.exceptions` gives API errors a
  stable `{code, message, correlation_id}` shape and never leaks a
  traceback to the client outside `DEBUG=True`.
- **Security headers (production):** `SECURE_HSTS_SECONDS`,
  `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`,
  `SECURE_SSL_REDIRECT` — all in `config/settings/production.py`, all
  inert until that settings module is actually used (never in
  development).
- **Fail-loud production config:** `production.py` raises at import time
  if `DJANGO_SECRET_KEY`/`DJANGO_ALLOWED_HOSTS` aren't explicitly set,
  rather than silently falling back to an insecure default.

## Implemented (Phase 7)

- **Multi-factor authentication** — TOTP (RFC 6238), hand-implemented
  algorithm with no external dependency (`apps.accounts.totp`), 6-digit
  codes, 30-second period, ±1 period drift window. A user with a
  confirmed `MFADevice` is intercepted after a correct password and is
  not granted a session until they also supply a valid code
  (`apps.accounts.views.mfa_verify`). Setup renders a real scannable QR
  code (`qrcode` package, SVG output, no Pillow dependency), with the raw
  secret/`otpauth://` URI available as a manual-entry fallback — see
  ADR-028 (supersedes ADR-025, which originally deferred the QR image).
- **Backup/recovery codes** — 10 single-use codes issued once MFA is
  confirmed, shown exactly once. Stored as a keyed HMAC-SHA256 lookup hash
  (`apps.accounts.models._backup_code_lookup_hash`), not PBKDF2 — see
  ADR-027 for why a high-entropy random token doesn't need (and, as a live
  test measurement showed, really shouldn't use) a deliberately-slow
  password hash, and for the incident that prompted the redesign.
- **Login and MFA brute-force lockout** — cache-backed counters
  (`apps.accounts.throttle`), 5 failed attempts locks out further tries
  for 15 minutes, keyed per (client IP, submitted email) for login and per
  user for MFA code entry.
- **CI pipeline** — GitHub Actions (`.github/workflows/ci.yml`) runs on
  every push/PR: `manage.py check`, `check --deploy` against production
  settings, migrations, the full pytest suite, static analysis of
  KUSANYA's own code (Bandit, blocking — see ADR-029), and an
  informational `pip-audit` dependency scan (see ADR-026 for why *that*
  doesn't fail the build — a deliberately different posture from Bandit).
- **Structured JSON logging** — production-only
  (`apps.core.logging.JsonFormatter`), one JSON object per line, carries
  the existing correlation ID.
- **Deeper health check** — `/healthz/` independently pings PostgreSQL,
  the cache, and the Celery broker (previously database + cache only).
- **General request rate limiting** — `apps.core.ratelimit.RequestRateLimitMiddleware`
  covers ordinary portal/dashboard requests (120/minute per user or IP by
  default), on top of the existing login/MFA lockout and the API's own
  DRF throttling. Fails open on a cache outage. See ADR-030.
- **Scheduled health monitoring with alerting** — `apps.core.tasks.monitor_system_health`
  runs the same database/cache/Celery-broker checks as `/healthz/` on a
  5-minute Celery Beat schedule and emails `settings.ADMINS`
  (`PLATFORM_ALERT_EMAILS` env var) when something's down — so a failure
  is noticed even with no external uptime monitor configured. Real
  outbound email requires `EMAIL_HOST`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`
  to actually be set in production (inert, same pattern as `SENTRY_DSN`,
  until they are). See ADR-031.

## Configured but not yet exercised

- **HTTPS/TLS termination** — assumed to happen at a reverse proxy /
  load balancer in front of the app (see [DEPLOYMENT.md](DEPLOYMENT.md));
  `SECURE_PROXY_SSL_HEADER` is set for that topology but no such proxy is
  deployed in Phase 1's local dev setup.
- **Secret management** — `.env`/environment variables today
  (`.env.example` documents every var, `.env` is gitignored); a real
  secrets manager (Vault, cloud provider secret store) is a production
  deployment concern, not built in Phase 1.

## Explicitly not implemented yet

- **Field-level encryption** — no encrypted model fields yet; nothing in
  the current data model (email, names, tenant contact info) is currently
  classified as requiring it, but payment-adjacent PII should be
  revisited against Tanzania's Personal Data Protection Act obligations —
  see [compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md).
- **APM / intrusion detection / external uptime monitoring** — still
  nothing. `SENTRY_DSN` remains a wiring point in `production.py`, inert
  until a DSN is provisioned; and nothing external polls `/healthz/` —
  see ADR-031 for what *does* now cover the gap (a scheduled internal
  check), which is a real but partial answer, not a substitute for
  either.
- **MFA is opt-in, not enforced** — a confirmed `MFADevice` gates login,
  but nothing requires platform staff or tenant staff to enable one.
  Making MFA mandatory for specific roles (e.g. platform staff) is a
  policy decision for a future phase, not a technical gap.

## What this document is not claiming

Implementing these controls does not constitute PCI-DSS, ISO 27001, SOC
2, Bank of Tanzania, PDPA, or TCRA compliance. None of those are claimed
anywhere in this codebase. Compliance requires a separate, formal
assessment against each framework's actual requirements — see
[compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md).
