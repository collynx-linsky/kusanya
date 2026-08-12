from django.urls import path

from apps.billing import views

app_name = "billing"

urlpatterns = [
    path("", views.bill_list, name="list"),
    path("new/", views.bill_create, name="create"),
    path("<uuid:pk>/", views.bill_detail, name="detail"),
    path("<uuid:pk>/cancel/", views.bill_cancel, name="cancel"),
    path("<uuid:pk>/control-number/", views.bill_request_control_number, name="request-control-number"),
]
