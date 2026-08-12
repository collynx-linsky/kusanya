"""
Server-side authorization helpers for tenant- and platform-level RBAC.

These are the single source of truth for "can this user do this" — views
call into them rather than re-implementing role checks inline, and
templates use them only to decide what to *show*, never as the actual
access-control boundary (build spec section 8: "Do not hard-code
permission checks only in templates").
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

from apps.tenants.models import TenantMembership
from apps.users.models import PlatformMembership


def user_platform_roles(user) -> set[str]:
    if not user.is_authenticated:
        return set()
    return set(
        PlatformMembership.objects.filter(user=user, is_active=True).values_list("role", flat=True)
    )


def has_platform_role(user, *roles: str) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return bool(user_platform_roles(user) & set(roles))


def get_tenant_role(user, tenant) -> str | None:
    if not user.is_authenticated or tenant is None:
        return None
    membership = TenantMembership.objects.filter(
        user=user, tenant=tenant, is_active=True
    ).first()
    return membership.role if membership else None


def has_tenant_role(user, tenant, *roles: str) -> bool:
    role = get_tenant_role(user, tenant)
    return role is not None and role in roles


def require_platform_role(*roles: str):
    """View decorator: 403s unless the user holds one of `roles` (or is superuser)."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not has_platform_role(request.user, *roles):
                raise PermissionDenied("This action requires a platform role you do not hold.")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def require_tenant_role(*roles: str):
    """View decorator: 403s unless the user holds one of `roles` on request.tenant.

    Must run after TenantResolutionMiddleware has set `request.tenant`.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            tenant = getattr(request, "tenant", None)
            if tenant is None or not has_tenant_role(request.user, tenant, *roles):
                raise PermissionDenied("This action requires a tenant role you do not hold.")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
