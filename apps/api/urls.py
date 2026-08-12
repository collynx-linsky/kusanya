"""External API v1. See docs/API_ARCHITECTURE.md.

`/transactions/` is deliberately not a separate route — a "transaction"
in build spec section 22's vocabulary is exactly what this codebase calls
a `Payment`; exposing two URLs for the same resource would just create
ambiguity about which one is canonical. See docs/API_ARCHITECTURE.md.
"""

from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.api import views

app_name = "api"

urlpatterns = [
    # OpenAPI schema + interactive docs.
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
    # v1
    path("v1/institutions/me/", views.InstitutionMeView.as_view(), name="institution-me"),
    path("v1/customers/", views.CustomerListCreateView.as_view(), name="customer-list"),
    path("v1/customers/<uuid:pk>/", views.CustomerDetailView.as_view(), name="customer-detail"),
    path("v1/accounts/", views.AccountListCreateView.as_view(), name="account-list"),
    path("v1/bills/", views.BillListCreateView.as_view(), name="bill-list"),
    path("v1/bills/<uuid:pk>/", views.BillDetailView.as_view(), name="bill-detail"),
    path("v1/bills/<uuid:pk>/control-number/", views.BillControlNumberView.as_view(), name="bill-control-number"),
    path("v1/payments/", views.PaymentListCreateView.as_view(), name="payment-list"),
    path("v1/payments/<uuid:pk>/", views.PaymentDetailView.as_view(), name="payment-detail"),
    path("v1/payments/<uuid:pk>/query/", views.PaymentQueryView.as_view(), name="payment-query"),
    path("v1/reconciliation/", views.ReconciliationRunListView.as_view(), name="reconciliation-list"),
    path("v1/settlements/", views.SettlementBatchListView.as_view(), name="settlement-list"),
    path("v1/settlements/<uuid:pk>/", views.SettlementBatchDetailView.as_view(), name="settlement-detail"),
    path("v1/webhooks/", views.WebhookEndpointListCreateView.as_view(), name="webhook-list"),
    path("v1/notifications/", views.NotificationListView.as_view(), name="notification-list"),
]
