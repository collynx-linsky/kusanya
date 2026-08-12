from django.urls import path

from apps.ledger import views

app_name = "ledger"

urlpatterns = [
    path("", views.ledger_list, name="list"),
]
