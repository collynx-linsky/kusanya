"""Production settings.

Fails loudly at import time if critical secrets are missing rather than
silently falling back to an insecure default — a production deploy with an
unset SECRET_KEY or DATABASE_URL should never start.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

SECRET_KEY = env("DJANGO_SECRET_KEY")  # no default — must be set
# Guard comparison against the known-insecure default, not a stored credential.
if SECRET_KEY == "insecure-dev-key-change-me":  # nosec B105
    raise RuntimeError("DJANGO_SECRET_KEY must be set explicitly in production.")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")  # no default — must be set

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Real SMTP wiring point for both apps.notifications' email channel and
# platform alert emails (apps.core.tasks.monitor_system_health). Same
# "inert until deployed with real config" pattern as SENTRY_DSN below —
# with no EMAIL_HOST set, Django's SMTP backend will simply fail to
# connect rather than silently pretend to send.
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)

# Structured (one-JSON-object-per-line) logging — see
# apps/core/logging.py::JsonFormatter and docs/SECURITY_ARCHITECTURE.md.
# Only the formatter changes; handlers/filters/loggers are inherited from
# base.py unmodified.
LOGGING["formatters"]["json"] = {"()": "apps.core.logging.JsonFormatter"}
LOGGING["handlers"]["console"]["formatter"] = "json"

# Sentry (or equivalent) wiring point — intentionally not activated until a
# DSN is actually provisioned. See docs/DEPLOYMENT.md.
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        send_default_pii=False,
    )
