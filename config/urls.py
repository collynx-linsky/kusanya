"""
KUSANYA root URL configuration.

Phase 1 exposes: platform admin (Django admin), authentication, tenant
onboarding/portal shell, and health checks. The external REST API
(/api/v1/...) is introduced in Phase 6 once billing/payments/ledger exist
to expose.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
    path("", include("apps.tenants.urls")),
    path("customers/", include("apps.customers.urls")),
    path("bills/", include("apps.billing.urls")),
    path("control-numbers/", include("apps.control_numbers.urls")),
    path("payments/", include("apps.payments.urls")),
    path("webhooks/", include("apps.webhooks.urls")),
    path("ledger/", include("apps.ledger.urls")),
    path("revenue/", include("apps.revenue.urls")),
    path("reconciliation/", include("apps.reconciliation.urls")),
    path("settlement/", include("apps.settlement.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("receipts/", include("apps.receipts.urls")),
    path("reports/", include("apps.reports.urls")),
    path("audit/", include("apps.audit.urls")),
    path("api-credentials/", include("apps.api.portal_urls")),
    path("api/", include("apps.api.urls")),
]

if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
