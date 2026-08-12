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
]

if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
