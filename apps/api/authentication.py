"""
API credential authentication. `Authorization: Bearer <key_id>.<secret>`.

Sets `request.tenant` directly from the authenticated credential — the
exact same rule as session-based tenant resolution
(apps.tenants.middleware.TenantResolutionMiddleware), just via a
different credential type. A tenant ID in the request body/query string
is never consulted for this purpose, anywhere in the API — see
docs/MULTI_TENANCY.md.
"""

from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.api.models import ApiCredential
from apps.tenants.models import Tenant


class ApiKeyAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith(f"{self.keyword} "):
            return None  # not this scheme — let DRF report "not authenticated"

        token = header[len(self.keyword) + 1 :].strip()
        if "." not in token:
            raise AuthenticationFailed("Malformed API credential.")
        key_id, _, raw_secret = token.partition(".")

        try:
            credential = ApiCredential.objects.select_related("tenant").get(key_id=key_id)
        except ApiCredential.DoesNotExist:
            raise AuthenticationFailed("Invalid API credential.")

        if not credential.is_active:
            raise AuthenticationFailed("This API credential has been revoked.")
        if not credential.check_secret(raw_secret):
            raise AuthenticationFailed("Invalid API credential.")
        if credential.tenant.status != Tenant.Status.ACTIVE:
            raise AuthenticationFailed("This institution is not active.")

        credential.mark_used()
        request.tenant = credential.tenant
        request.api_credential = credential
        return (AnonymousUser(), credential)

    def authenticate_header(self, request):
        return self.keyword
