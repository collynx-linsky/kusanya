"""
Core, sector-agnostic views: health checks and the post-login dashboard
router. Platform dashboards and tenant dashboards are separate views/apps —
this module only decides which one a given authenticated user lands on.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render

from apps.core.healthchecks import run_health_checks

logger = logging.getLogger("kusanya")


def home(request):
    """Root URL: bounce to the dashboard router (which enforces login) or
    straight to login for anonymous visitors."""
    if request.user.is_authenticated:
        return redirect("core:dashboard-router")
    return redirect("accounts:login")


def health_check(request):
    """Liveness/readiness probe. Unauthenticated by design (infra probes).

    Checks every hard dependency a request or a background task actually
    relies on: PostgreSQL, Redis-as-cache, and Redis-as-Celery-broker.
    The cache and broker checks are against the same Redis instance in
    development but are deliberately checked independently — they're
    logically separate concerns (a cache outage degrades performance; a
    broker outage means nothing in apps.webhooks/apps.notifications/etc.
    ever gets delivered) and could point at different instances in a
    real deployment.

    This is the passive half of monitoring — something external has to
    actually poll it. apps.core.tasks.monitor_system_health is the active
    half: a Celery Beat task that runs the same checks on a schedule and
    emails platform admins on failure, so a failure is noticed even if
    nothing is polling this endpoint. See ARCHITECTURE_DECISIONS ADR-031.
    """
    healthy, checks = run_health_checks()
    return JsonResponse(
        {"status": "ok" if healthy else "unhealthy", "checks": checks},
        status=200 if healthy else 503,
    )


@login_required
def dashboard_router(request):
    """Sends an authenticated user to the dashboard appropriate for them.

    - Platform staff (request.user.is_staff) → platform dashboard.
    - Users with exactly one active tenant membership → that tenant's
      dashboard.
    - Users with more than one → a tenant picker (not yet implemented in
      Phase 1; falls back to the first membership with a warning logged).
    - Users with none → a plain "no access yet" page instead of a crash.
    """
    from apps.tenants.models import TenantMembership

    if request.user.is_staff:
        return redirect("core:platform-dashboard")

    memberships = TenantMembership.objects.filter(
        user=request.user, is_active=True
    ).select_related("tenant")

    if not memberships.exists():
        return render(request, "dashboard/no_access.html")

    if memberships.count() > 1:
        logger.info(
            "User %s has multiple tenant memberships; tenant picker not yet "
            "implemented, defaulting to first.",
            request.user.pk,
        )

    membership = memberships.first()
    request.session["active_tenant_id"] = str(membership.tenant_id)
    return redirect("tenants:dashboard")


@login_required
def platform_dashboard(request):
    if not request.user.is_staff:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("Platform dashboard is restricted to platform staff.")

    from django.db.models import Sum

    from apps.payments.models import Payment, PaymentStatus
    from apps.reconciliation.models import ExceptionStatus, ReconciliationException
    from apps.revenue.models import RevenueEvent
    from apps.tenants.models import Tenant, TenantMembership

    context = {
        "total_tenants": Tenant.objects.count(),
        "active_tenants": Tenant.objects.filter(status=Tenant.Status.ACTIVE).count(),
        "pending_tenants": Tenant.objects.filter(status=Tenant.Status.PENDING).count(),
        "total_users_with_access": TenantMembership.objects.filter(is_active=True).count(),
        "total_platform_revenue": RevenueEvent.objects.aggregate(total=Sum("amount"))["total"] or 0,
        "successful_payment_count": Payment.objects.filter(status=PaymentStatus.SUCCESSFUL).count(),
        "open_reconciliation_exceptions": ReconciliationException.objects.filter(
            status=ExceptionStatus.OPEN
        ).count(),
    }
    return render(request, "dashboard/platform_dashboard.html", context)
