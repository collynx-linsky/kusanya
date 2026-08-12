from django.urls import path

from apps.settlement import views

app_name = "settlement"

urlpatterns = [
    path("", views.batch_list, name="list"),
    path("<uuid:pk>/", views.batch_detail, name="detail"),
    path("platform/", views.platform_batch_list, name="platform-list"),
    path("platform/generate/", views.generate_batch, name="generate"),
    path("platform/<uuid:pk>/complete/", views.mark_completed, name="mark-completed"),
]
