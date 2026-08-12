from django.urls import path

from apps.api import portal_views

app_name = "api_credentials"

urlpatterns = [
    path("", portal_views.credential_list, name="list"),
    path("new/", portal_views.credential_create, name="create"),
    path("<uuid:pk>/rotate/", portal_views.credential_rotate, name="rotate"),
    path("<uuid:pk>/revoke/", portal_views.credential_revoke, name="revoke"),
]
