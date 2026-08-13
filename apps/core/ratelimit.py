"""General request-rate limiting for the web/portal surface.

Distinct from, and in addition to, two things that already exist:
- apps.accounts.throttle — targeted brute-force lockout on login/MFA,
  keyed by (IP, email) or user, with a long (15-minute) penalty.
- apps.api's DRF throttling (Phase 6) — per-ApiCredential limits on the
  external API, already appropriate for that surface and left alone.

This middleware covers everything else: ordinary authenticated (and
anonymous) requests to portal/dashboard views, which had no rate
limiting at all — see docs/SECURITY_ARCHITECTURE.md and
ARCHITECTURE_DECISIONS ADR-030.
"""

import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

from apps.audit.context import client_ip_from_request

logger = logging.getLogger("kusanya")

_CACHE_KEY_PREFIX = "request_rate_limit"


def _client_key(request) -> str:
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        return f"user:{request.user.pk}"
    ip = client_ip_from_request(request) or "unknown"
    return f"ip:{ip}"


class RequestRateLimitMiddleware:
    """Fixed-window counter per client, per window. Deliberately generous
    (see REQUEST_RATE_LIMIT in settings) — this exists to blunt scripted
    abuse of ordinary views (e.g. hammering a bill-lookup or
    control-number page), not to constrain normal interactive use, which
    is already covered by the tighter, purpose-specific throttles above.

    Fails open: a cache error never blocks a real request. Rate limiting
    is a defense-in-depth control, not a correctness guarantee — an
    outage in the rate limiter should never become an outage in the app
    itself.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.limit = getattr(settings, "REQUEST_RATE_LIMIT", 120)
        self.window_seconds = getattr(settings, "REQUEST_RATE_LIMIT_WINDOW_SECONDS", 60)
        self.exempt_prefixes = tuple(getattr(settings, "REQUEST_RATE_LIMIT_EXEMPT_PREFIXES", ()))

    def __call__(self, request):
        if not self.limit or request.path.startswith(self.exempt_prefixes):
            return self.get_response(request)

        key = f"{_CACHE_KEY_PREFIX}:{_client_key(request)}"
        try:
            count = cache.get(key, 0)
        except Exception:  # noqa: BLE001 — cache outage must not break the app
            logger.warning("Rate limit cache read failed; failing open.")
            return self.get_response(request)

        if count >= self.limit:
            logger.warning("Rate limit exceeded for %s on %s", _client_key(request), request.path)
            return HttpResponse(
                "Too many requests. Please slow down and try again shortly.",
                status=429,
                content_type="text/plain",
            )

        try:
            if count == 0:
                cache.set(key, 1, timeout=self.window_seconds)
            else:
                cache.incr(key)
        except Exception:  # noqa: BLE001
            logger.warning("Rate limit cache write failed; failing open for this request.")

        return self.get_response(request)
