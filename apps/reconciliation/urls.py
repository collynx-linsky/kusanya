from django.urls import path

from apps.reconciliation import views

app_name = "reconciliation"

urlpatterns = [
    path("", views.run_list, name="list"),
    path("run/", views.trigger_run, name="trigger"),
    path("<uuid:pk>/", views.run_detail, name="detail"),
    path("exceptions/<uuid:pk>/resolve/", views.resolve_exception_view, name="resolve-exception"),
]
