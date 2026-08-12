from django.contrib import admin

from apps.receipts.models import Receipt


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ["receipt_number", "tenant", "customer_name", "amount", "currency", "issued_at"]
    list_filter = ["tenant"]
    search_fields = ["receipt_number", "customer_name", "payment_reference", "control_number"]
    autocomplete_fields = ["tenant", "payment"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
