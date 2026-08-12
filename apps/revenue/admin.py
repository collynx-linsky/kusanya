from django.contrib import admin

from apps.revenue.models import RevenueEvent


@admin.register(RevenueEvent)
class RevenueEventAdmin(admin.ModelAdmin):
    """Read-only — revenue events are immutable (see models.py)."""

    list_display = ["created_at", "tenant", "event_type", "amount", "currency"]
    list_filter = ["event_type", "tenant"]
    search_fields = ["correlation_id"]
    autocomplete_fields = ["tenant", "ledger_entry"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
