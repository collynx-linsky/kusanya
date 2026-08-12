from django.urls import path

from apps.payments import views

app_name = "payments"

urlpatterns = [
    path("", views.payment_list, name="list"),
    path("<uuid:pk>/", views.payment_detail, name="detail"),
    path("<uuid:pk>/query/", views.payment_query, name="query"),
    path("<uuid:pk>/refund/", views.payment_refund, name="refund"),
    path("<uuid:pk>/reverse/", views.payment_reverse, name="reverse"),
    path("bills/<uuid:bill_pk>/pay/", views.pay_bill, name="pay-bill"),
    path("providers/mock/callback/", views.mock_provider_callback, name="mock-provider-callback"),
]
