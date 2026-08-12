"""Local development settings. Loose security, verbose errors, debug tooling."""

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, INSTALLED_APPS, env

DEBUG = True

INSTALLED_APPS += ["django_extensions"]

try:
    import debug_toolbar  # noqa: F401

    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE
    INTERNAL_IPS = ["127.0.0.1"]
except ImportError:
    pass

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Relaxed for local HTTP development only — production.py hardens these.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
