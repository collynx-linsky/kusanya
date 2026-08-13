from django.urls import path

from apps.accounts import portal_views, views

app_name = "accounts"

urlpatterns = [
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("logout/", views.KusanyaLogoutView.as_view(), name="logout"),
    path("mfa/verify/", views.mfa_verify, name="mfa-verify"),
    path("mfa/", portal_views.mfa_status, name="mfa-status"),
    path("mfa/setup/", portal_views.mfa_setup, name="mfa-setup"),
    path("mfa/disable/", portal_views.mfa_disable, name="mfa-disable"),
    path("mfa/backup-codes/regenerate/", portal_views.mfa_regenerate_backup_codes, name="mfa-backup-codes-regenerate"),
]
