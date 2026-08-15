from django.urls import path

from apps.users import views

app_name = "users"

urlpatterns = [
    path("platform/", views.platform_users, name="platform-list"),
    path("platform/create/", views.platform_user_create, name="platform-create"),
]
