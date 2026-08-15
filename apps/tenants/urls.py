from django.urls import path

from apps.tenants import views

app_name = "tenants"

urlpatterns = [
    path("register/", views.onboard, name="onboard"),
    path("portal/", views.dashboard, name="dashboard"),
    path("team/", views.team_members, name="team"),
    path("team/add/", views.team_member_create, name="team-member-create"),
    path("team/<uuid:pk>/deactivate/", views.team_member_deactivate, name="team-member-deactivate"),
    path("team/<uuid:pk>/activate/", views.team_member_activate, name="team-member-activate"),
    path("platform/tenants/pending/", views.pending_tenants, name="pending-tenants"),
    path("platform/tenants/create/", views.platform_create_tenant, name="platform-create-tenant"),
    path("platform/tenants/<uuid:pk>/approve/", views.approve_tenant, name="approve-tenant"),
]
