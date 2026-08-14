from django.urls import path

from apps.tenants import views

app_name = "tenants"

urlpatterns = [
    path("register/", views.onboard, name="onboard"),
    path("portal/", views.dashboard, name="dashboard"),
    path("platform/tenants/pending/", views.pending_tenants, name="pending-tenants"),
    path("platform/tenants/create/", views.platform_create_tenant, name="platform-create-tenant"),
    path("platform/tenants/<uuid:pk>/approve/", views.approve_tenant, name="approve-tenant"),
]
