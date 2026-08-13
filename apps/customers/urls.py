from django.urls import path

from apps.customers import views

app_name = "customers"

urlpatterns = [
    path("", views.customer_list, name="list"),
    path("new/", views.customer_create, name="create"),
    path("<uuid:pk>/", views.customer_detail, name="detail"),
    path("<uuid:pk>/edit/", views.customer_edit, name="edit"),
    path("<uuid:pk>/deactivate/", views.customer_deactivate, name="deactivate"),
    path("<uuid:pk>/activate/", views.customer_activate, name="activate"),
    path("bulk-deactivate/", views.customer_bulk_deactivate, name="bulk-deactivate"),
    path("<uuid:customer_pk>/accounts/new/", views.account_create, name="account-create"),
]
