"""
Brute-force lockout for login and MFA code entry — build spec section 28
lists rate limiting as a required security control; this closes the gap
`docs/SECURITY_ARCHITECTURE.md` explicitly flagged as "no request
throttling on login or any endpoint yet."

Uses Django's cache (Redis in every real environment — see
config/settings/base.py), the same mechanism `apps.api.throttling`
already relies on for API rate limiting, so this needs no new
infrastructure.
"""

from django.core.cache import cache

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


def _key(scope: str, identifier: str) -> str:
    return f"auth_throttle:{scope}:{identifier}"


def is_locked_out(scope: str, identifier: str) -> bool:
    return cache.get(_key(scope, identifier), 0) >= MAX_ATTEMPTS


def record_failure(scope: str, identifier: str) -> int:
    key = _key(scope, identifier)
    count = cache.get(key, 0) + 1
    cache.set(key, count, timeout=LOCKOUT_SECONDS)
    return count


def reset(scope: str, identifier: str) -> None:
    cache.delete(_key(scope, identifier))
