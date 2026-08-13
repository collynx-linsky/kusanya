from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz/", views.health_check, name="health-check"),
    path("dashboard/", views.dashboard_router, name="dashboard-router"),
    path("dashboard/platform/", views.platform_dashboard, name="platform-dashboard"),
    path("command-palette/search/", views.command_palette_search, name="command-palette-search"),
    path("background-jobs/", views.background_jobs, name="background-jobs"),
]
