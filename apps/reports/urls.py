from django.urls import path

from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("", views.reports_index, name="index"),
    path("bills/", views.bills_report, name="bills"),
    path("payments/", views.payments_report, name="payments"),
    path("collections/", views.collections_report, name="collections"),
    path("outstanding-balances/", views.outstanding_balances_report, name="outstanding-balances"),
    path("audit/", views.audit_report, name="audit"),
]
