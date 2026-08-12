"""Rate limiting per API credential (build spec section 23). Keyed by
`key_id`, not by IP — an ERP integration typically calls from a fixed
server, but limiting by credential is the correct unit regardless (two
integrations sharing an egress IP shouldn't throttle each other)."""

from rest_framework.throttling import SimpleRateThrottle


class ApiCredentialRateThrottle(SimpleRateThrottle):
    scope = "api_credential"

    def get_cache_key(self, request, view):
        credential = getattr(request, "api_credential", None)
        if credential is None:
            return None  # unauthenticated — permission check rejects it separately
        return self.cache_format % {"scope": self.scope, "ident": credential.key_id}
