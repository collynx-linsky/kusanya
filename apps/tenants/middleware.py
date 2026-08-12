"""
Tenant resolution for the server-rendered portal.

IMPORTANT: this resolves `request.tenant` from the authenticated user's
*active membership row*, never from a tenant ID supplied by the client
(query string, form field, header). A session key merely records which of
the user's own active tenants they last selected — it is re-validated
against TenantMembership on every request, so a stale/tampered session
value can, at worst, fall back to "no tenant selected", never to another
tenant's data. See docs/MULTI_TENANCY.md.

API-key-based tenant resolution for external integrations (Phase 6) will
live in apps.api and follows the same rule: derive tenant from the
authenticated credential, never trust a client-supplied tenant id.
"""

from apps.tenants.models import TenantMembership


class TenantResolutionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        request.tenant_membership = None

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            tenant_id = request.session.get("active_tenant_id")
            if tenant_id:
                membership = (
                    TenantMembership.objects.filter(
                        user=user, tenant_id=tenant_id, is_active=True
                    )
                    .select_related("tenant")
                    .first()
                )
                if membership is not None:
                    request.tenant = membership.tenant
                    request.tenant_membership = membership
                else:
                    # Session pointed at a tenant the user can no longer
                    # access — drop it rather than silently trusting it.
                    del request.session["active_tenant_id"]

        return self.get_response(request)
