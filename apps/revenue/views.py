from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import render

from apps.revenue.models import RevenueEvent
from apps.tenants.permissions import require_platform_role
from apps.users.models import PlatformRole


@login_required
def tenant_revenue_summary(request):
    """Finance dashboard (build spec section 26): gross platform revenue
    this tenant has generated, broken down by event type — every event
    type is shown, including the zero-fee ones, so "how many control
    numbers were reused" is visible alongside "how much did KUSANYA earn
    from us."."""
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")

    breakdown = (
        RevenueEvent.objects.filter(tenant=request.tenant)
        .values("event_type")
        .annotate(total_amount=Sum("amount"), event_count=Count("id"))
        .order_by("event_type")
    )
    total_revenue = sum((row["total_amount"] for row in breakdown), start=0)

    return render(
        request,
        "revenue/summary.html",
        {"breakdown": breakdown, "total_revenue": total_revenue},
    )


@login_required
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.FINANCE_ADMIN)
def platform_revenue_dashboard(request):
    """Platform-wide revenue across every tenant — build spec section 26's
    platform dashboard requirement."""
    breakdown = (
        RevenueEvent.objects.values("event_type")
        .annotate(total_amount=Sum("amount"), event_count=Count("id"))
        .order_by("event_type")
    )
    total_revenue = sum((row["total_amount"] for row in breakdown), start=0)

    by_tenant = (
        RevenueEvent.objects.values("tenant__name")
        .annotate(total_amount=Sum("amount"))
        .order_by("-total_amount")[:20]
    )

    return render(
        request,
        "revenue/platform_dashboard.html",
        {"breakdown": breakdown, "total_revenue": total_revenue, "by_tenant": by_tenant},
    )
