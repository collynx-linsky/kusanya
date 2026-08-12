from django.urls import path

from apps.receipts import views

app_name = "receipts"

urlpatterns = [
    path("", views.receipt_list, name="list"),
    path("<uuid:pk>/", views.receipt_detail, name="detail"),
]
