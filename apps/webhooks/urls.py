from django.urls import path

from apps.webhooks import views

app_name = "webhooks"

urlpatterns = [
    path("", views.endpoint_list, name="list"),
    path("new/", views.endpoint_create, name="create"),
    path("<uuid:pk>/deliveries/", views.endpoint_deliveries, name="deliveries"),
]
