from django.conf import settings


def branding(request):
    return {
        "KUSANYA_BRAND_NAME": settings.KUSANYA_BRAND_NAME,
        "KUSANYA_TAGLINE": settings.KUSANYA_TAGLINE,
    }


def topbar_alerts(request):
    """Backs the top bar's notification bell (P1 item 12) — deliberately
    a live-computed view of genuinely real, already-existing state
    (open reconciliation exceptions, pending tenant approvals), not a
    stored/historical notification inbox. Building a fake "you have 3
    notifications" feed with no real backing data would violate this
    project's own "no fake functionality" rule; this is the honest
    version of that feature — see docs/DESIGN_SYSTEM.md.

    Runs on every authenticated request, so the queries here are
    deliberately cheap (COUNT + a LIMIT 5 slice, nothing heavier) and
    skipped entirely for anonymous requests or requests where neither
    audience applies.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}

    alerts = []

    from apps.accounts.models import MFADevice

    if not MFADevice.objects.filter(user=request.user, confirmed=True).exists():
        alerts.append(
            {
                "icon": "bi-shield-exclamation",
                "level": "warning",
                "text": "Two-factor authentication isn't enabled on your account",
                "url_name": "accounts:mfa-status",
            }
        )

    tenant = getattr(request, "tenant", None)
    if tenant is not None:
        from apps.reconciliation.models import ExceptionStatus, ReconciliationException

        open_exceptions = ReconciliationException.objects.filter(tenant=tenant, status=ExceptionStatus.OPEN)
        count = open_exceptions.count()
        if count:
            alerts.append(
                {
                    "icon": "bi-exclamation-triangle-fill",
                    "level": "warning",
                    "text": f"{count} open reconciliation exception{'s' if count != 1 else ''}",
                    "url_name": "reconciliation:list",
                }
            )

    if request.user.is_staff:
        from apps.tenants.models import Tenant

        pending_count = Tenant.objects.filter(status=Tenant.Status.PENDING).count()
        if pending_count:
            alerts.append(
                {
                    "icon": "bi-building-add",
                    "level": "info",
                    "text": f"{pending_count} institution{'s' if pending_count != 1 else ''} awaiting approval",
                    "url_name": "tenants:pending-tenants",
                }
            )

    return {"topbar_alerts": alerts}
