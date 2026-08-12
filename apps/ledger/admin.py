from django.contrib import admin

from apps.ledger.models import LedgerEntry


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    """Read-only — ledger entries are immutable (see models.py)."""

    list_display = ["created_at", "tenant", "entry_type", "account", "amount", "currency", "reference"]
    list_filter = ["entry_type", "account", "tenant"]
    search_fields = ["reference", "correlation_id"]
    autocomplete_fields = ["tenant", "related_entry"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
