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

- **MFA** — no second factor. "MFA-ready" means the auth stack doesn't
  preclude adding it (Django's `django-otp` or similar would slot into
  the existing `AuthenticationMiddleware` chain), not that it exists.
- **Rate limiting** — no request throttling on login or any endpoint yet.
  Needed before production, especially on `/accounts/login/` and any
  future API token endpoints.
- **Field-level encryption** — no encrypted model fields yet; nothing in
  Phase 1's data model (email, names, tenant contact info) is currently
  classified as requiring it, but payment-adjacent PII in later phases
  should be revisited against Tanzania's Personal Data Protection Act
  obligations — see [compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md).
- **API authentication** (API keys, secret rotation, request signing) —
  doesn't exist yet; there is no external API surface yet (Phase 6).
- **Webhook signature verification** — doesn't exist yet; no webhooks
  exist yet (Phase 3/6).
- **Automated security testing** (SAST/dependency scanning in CI) — no CI
  pipeline exists yet.
- **Monitoring/alerting, intrusion detection** — out of scope for Phase
  1; `apps.core.views.health_check` exists as the integration point for a
  future uptime monitor, nothing more.

## What this document is not claiming

Implementing these controls does not constitute PCI-DSS, ISO 27001, SOC
2, Bank of Tanzania, PDPA, or TCRA compliance. None of those are claimed
anywhere in this codebase. Compliance requires a separate, formal
assessment against each framework's actual requirements — see
[compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md).
