from django.urls import path

from apps.revenue import views

app_name = "revenue"

urlpatterns = [
    path("", views.tenant_revenue_summary, name="summary"),
    path("platform/", views.platform_revenue_dashboard, name="platform-dashboard"),
]
