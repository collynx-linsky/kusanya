from django.urls import path

from apps.audit import views

app_name = "audit"

urlpatterns = [
    path("platform/verify-chain/", views.verify_chain, name="verify-chain"),
]
