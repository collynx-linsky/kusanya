"""
Core, sector-agnostic views: health checks and the post-login dashboard
router. Platform dashboards and tenant dashboards are separate views/apps —
this module only decides which one a given authenticated user lands on.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.core.healthchecks import run_health_checks

logger = logging.getLogger("kusanya")

# Static navigation shortcuts for the command palette (docs/DESIGN_SYSTEM.md)
# -- mirrors partials/sidebar.html's real links, not a separate source of
# truth invented for the palette.
_NAV_SHORTCUTS = [
    {"label": "Dashboard", "icon": "bi-speedometer2", "url_name": "core:dashboard-router"},
    {"label": "Customers", "icon": "bi-people", "url_name": "customers:list"},
    {"label": "New customer", "icon": "bi-person-plus", "url_name": "customers:create"},
    {"label": "Bills", "icon": "bi-receipt", "url_name": "billing:list"},
    {"label": "New bill", "icon": "bi-receipt", "url_name": "billing:create"},
    {"label": "Control numbers", "icon": "bi-hash", "url_name": "control_numbers:list"},
    {"label": "Payments", "icon": "bi-credit-card", "url_name": "payments:list"},
    {"label": "Ledger", "icon": "bi-journal-text", "url_name": "ledger:list"},
    {"label": "Revenue", "icon": "bi-graph-up", "url_name": "revenue:summary"},
    {"label": "Reconciliation", "icon": "bi-check2-square", "url_name": "reconciliation:list"},
    {"label": "Settlements", "icon": "bi-bank", "url_name": "settlement:list"},
    {"label": "Webhooks", "icon": "bi-broadcast", "url_name": "webhooks:list"},
    {"label": "Notifications", "icon": "bi-bell", "url_name": "notifications:list"},
    {"label": "Receipts", "icon": "bi-file-earmark-text", "url_name": "receipts:list"},
    {"label": "Reports", "icon": "bi-bar-chart", "url_name": "reports:index"},
    {"label": "Audit events", "icon": "bi-clock-history", "url_name": "reports:audit"},
    {"label": "API credentials", "icon": "bi-key", "url_name": "api_credentials:list"},
    {"label": "Security settings", "icon": "bi-shield-lock", "url_name": "accounts:mfa-status"},
]


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


@login_required
def background_jobs(request):
    """Real visibility into background/async work -- webhook and
    notification delivery status (both already Celery-task-driven, see
    apps.webhooks.tasks/apps.notifications.tasks) plus the scheduled
    health-monitor task's own run history (apps.core.tasks,
    django_celery_beat.PeriodicTask). Not a generic Celery task browser
    (that needs django-celery-results or Flower, a real infra decision
    for later) -- this surfaces exactly the background work KUSANYA
    itself already tracks in its own tables. See
    docs/DESIGN_SYSTEM.md's "Background jobs" section.
    """
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")

    from apps.notifications.models import Notification, NotificationStatus
    from apps.webhooks.models import WebhookDelivery, WebhookDeliveryStatus

    webhook_deliveries = WebhookDelivery.objects.filter(tenant=request.tenant)
    notifications = Notification.objects.filter(tenant=request.tenant)

    context = {
        "webhook_pending": webhook_deliveries.filter(
            status__in=[WebhookDeliveryStatus.PENDING, WebhookDeliveryStatus.RETRYING]
        ).count(),
        "webhook_delivered": webhook_deliveries.filter(status=WebhookDeliveryStatus.DELIVERED).count(),
        "webhook_dead_letter": webhook_deliveries.filter(status=WebhookDeliveryStatus.DEAD_LETTER).count(),
        "recent_webhook_deliveries": webhook_deliveries.select_related("endpoint").order_by("-created_at")[:10],
        "notification_pending": notifications.filter(status=NotificationStatus.PENDING).count(),
        "notification_sent": notifications.filter(status=NotificationStatus.SENT).count(),
        "notification_failed": notifications.filter(status=NotificationStatus.FAILED).count(),
    }

    if request.user.is_staff:
        from django_celery_beat.models import PeriodicTask

        context["scheduled_tasks"] = PeriodicTask.objects.filter(enabled=True).order_by("name")

    return render(request, "core/background_jobs.html", context)


@login_required
def command_palette_search(request):
    """Ctrl+K / Cmd+K palette results — real navigation shortcuts
    (mirroring the sidebar) plus, once the user's tenant is known, real
    entity search (same exact-match-on-encrypted-fields constraint as
    every other search in this codebase, ADR-032). Never fabricated
    results. See docs/DESIGN_SYSTEM.md."""
    from apps.core.search import search_bills, search_customers

    query = request.GET.get("q", "").strip()
    query_lower = query.lower()

    nav_matches = [item for item in _NAV_SHORTCUTS if query_lower in item["label"].lower()][:8] if query else []

    customer_matches, bill_matches = [], []
    if request.tenant is not None and query:
        customer_matches = search_customers(request.tenant, query)
        bill_matches = search_bills(request.tenant, query)

    return render(
        request,
        "components/_command_palette_results.html",
        {
            "query": query,
            "nav_matches": nav_matches,
            "customer_matches": customer_matches,
            "bill_matches": bill_matches,
        },
    )
