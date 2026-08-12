from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("logout/", views.KusanyaLogoutView.as_view(), name="logout"),
]
