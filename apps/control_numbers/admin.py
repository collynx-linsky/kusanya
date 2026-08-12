from django.contrib import admin

from apps.control_numbers.models import ControlNumber


@admin.register(ControlNumber)
class ControlNumberAdmin(admin.ModelAdmin):
    list_display = ["value", "tenant", "scope", "status", "bill", "customer_account", "created_at"]
    list_filter = ["scope", "status", "tenant"]
    search_fields = ["value", "bill__bill_number", "customer_account__name"]
    autocomplete_fields = ["tenant", "bill", "customer_account", "created_by"]
    readonly_fields = ["value", "created_at", "updated_at"]
