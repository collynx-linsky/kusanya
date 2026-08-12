from django.urls import path

from apps.customers import views

app_name = "customers"

urlpatterns = [
    path("", views.customer_list, name="list"),
    path("new/", views.customer_create, name="create"),
    path("<uuid:pk>/", views.customer_detail, name="detail"),
    path("<uuid:customer_pk>/accounts/new/", views.account_create, name="account-create"),
]
