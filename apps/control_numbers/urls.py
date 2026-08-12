from django.urls import path

from apps.control_numbers import views

app_name = "control_numbers"

urlpatterns = [
    path("", views.control_number_list, name="list"),
]
