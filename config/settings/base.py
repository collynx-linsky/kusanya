"""
KUSANYA — base Django settings.

Shared by every environment. Environment-specific settings modules
(development.py, testing.py, production.py) import * from this module and
override only what genuinely differs.

Nothing sector-specific belongs here. Nothing payment-provider-specific
belongs here (see apps/providers, introduced in Phase 3).
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)

# .env is optional — in containers/production, real env vars are supplied
# directly and no .env file is expected to exist.
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
    "django_filters",
    "django_celery_beat",
]

# KUSANYA domain apps. Phase 1 ships the platform foundation only:
# identity, tenancy, RBAC and audit. Billing/payments/ledger/etc. are
# introduced in later phases per docs/PRODUCT_REQUIREMENTS.md — see
# ARCHITECTURE_DECISIONS.md for why they are not stubbed in early.
LOCAL_APPS = [
    "apps.core",
    "apps.users",
    "apps.accounts",
    "apps.tenants",
    "apps.organizations",
    "apps.audit",
    # Phase 2 — customer, account, billing, control number:
    "apps.customers",
    "apps.billing",
    "apps.control_numbers",
    # Phase 3 — payment domain, provider abstraction, webhooks:
    "apps.providers",
    "apps.payments",
    "apps.webhooks",
    # Phase 4 — ledger, revenue, reconciliation, settlement:
    "apps.ledger",
    "apps.revenue",
    "apps.reconciliation",
    "apps.settlement",
    # Phase 5 — notifications, receipts, reports:
    "apps.notifications",
    "apps.receipts",
    "apps.reports",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # KUSANYA middleware, order matters:
    # 1. Correlation ID must exist before anything logs.
    # 2. Tenant resolution must run after auth (needs request.user) and
    #    before views execute.
    "apps.core.middleware.CorrelationIdMiddleware",
    "apps.tenants.middleware.TenantResolutionMiddleware",
    "apps.audit.middleware.AuditContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.tenants.context_processors.current_tenant",
                "apps.core.context_processors.branding",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# PostgreSQL is the only supported production database. NEVER use floating
# point for monetary columns — all money fields are DecimalField. See
# docs/DATABASE_ARCHITECTURE.md.

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://kusanya:kusanya@localhost:5432/kusanya",
    ),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

AUTH_USER_MODEL = "users.User"

# ---------------------------------------------------------------------------
# Cache / Redis / Celery
# ---------------------------------------------------------------------------

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"  # All timestamps stored in UTC; render in local tz in templates.
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / media
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Auth redirects
# ---------------------------------------------------------------------------

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard-router"
LOGOUT_REDIRECT_URL = "accounts:login"

# ---------------------------------------------------------------------------
# Django REST Framework / OpenAPI
# ---------------------------------------------------------------------------
# Phase 1 does not expose the external API surface yet (see docs section on
# phases). DRF is wired now so apps/api can be built on stable foundations
# in Phase 6 without a framework migration.

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.drf_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "KUSANYA API",
    "DESCRIPTION": "Digital Collections & Payment Infrastructure — external integration API.",
    "VERSION": "0.1.0-foundation",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ---------------------------------------------------------------------------
# Security baseline (tightened further in production.py)
# ---------------------------------------------------------------------------

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # must be readable by JS if HTMX needs the token
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# Structured-ish logging foundation. A real JSON formatter / log shipper is
# introduced with observability work (section 33) — this establishes the
# correlation-id-aware baseline so it can be swapped without touching call
# sites.

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlation_id": {
            "()": "apps.core.logging.CorrelationIdFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)s [%(correlation_id)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["correlation_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "kusanya": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# KUSANYA platform constants
# ---------------------------------------------------------------------------

from django.contrib.messages import constants as message_constants

MESSAGE_TAGS = {
    message_constants.ERROR: "danger",  # Bootstrap uses "danger", not "error"
}

KUSANYA_BRAND_NAME = "KUSANYA"
KUSANYA_TAGLINE = "Digital Collections & Payment Infrastructure"
KUSANYA_DEFAULT_CURRENCY = "TZS"
