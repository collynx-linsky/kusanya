"""Settings used by the automated test suite (pytest.ini points DJANGO_SETTINGS_MODULE here).

Fast, deterministic, isolated. Uses a dedicated test database and eager
Celery execution so async side effects are observable synchronously in
tests.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False
# Test-only settings module, structurally unreachable from production.py.
SECRET_KEY = "test-secret-key-not-for-production"  # nosec B105

# Password hashing is intentionally weakened only for test speed.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

# WhiteNoise's manifest storage requires `collectstatic` to have run so it
# has a manifest to resolve hashed filenames from. Tests don't run
# collectstatic, so fall back to plain (unhashed) static file resolution.
STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
