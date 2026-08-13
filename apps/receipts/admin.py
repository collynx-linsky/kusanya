from django.contrib import admin

from apps.core.encrypted_fields import EncryptedFieldSearchAdminMixin
from apps.receipts.models import Receipt


@admin.register(Receipt)
class ReceiptAdmin(EncryptedFieldSearchAdminMixin, admin.ModelAdmin):
    """customer_name is encrypted at rest (ADR-032) — search on it is
    exact-match only via its lookup_hash companion."""

    list_display = ["receipt_number", "tenant", "customer_name", "amount", "currency", "issued_at"]
    list_filter = ["tenant"]
    search_fields = ["receipt_number", "payment_reference", "control_number"]
    encrypted_exact_search_fields = ["customer_name"]
    autocomplete_fields = ["tenant", "payment"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
