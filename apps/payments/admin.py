from django.contrib import admin

from apps.core.encrypted_fields import EncryptedFieldSearchAdminMixin
from apps.payments.models import Payment, PaymentAllocation, PaymentCallbackEvent


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    readonly_fields = ["bill", "amount"]


@admin.register(Payment)
class PaymentAdmin(EncryptedFieldSearchAdminMixin, admin.ModelAdmin):
    """payer_reference is encrypted at rest (ADR-032) — search on it is
    exact-match only via its lookup_hash companion."""

    list_display = ["merchant_reference", "tenant", "amount", "currency", "status", "provider", "initiated_at"]
    list_filter = ["status", "provider", "tenant"]
    search_fields = ["merchant_reference", "provider_reference", "idempotency_key"]
    encrypted_exact_search_fields = ["payer_reference"]
    autocomplete_fields = ["tenant", "control_number", "provider", "channel"]
    readonly_fields = ["merchant_reference", "initiated_at", "completed_at"]
    inlines = [PaymentAllocationInline]


@admin.register(PaymentCallbackEvent)
class PaymentCallbackEventAdmin(admin.ModelAdmin):
    """Read-only — this is an inbound-event audit trail, not editable data."""

    list_display = ["provider", "external_event_id", "outcome", "payment", "created_at"]
    list_filter = ["outcome", "provider"]
    search_fields = ["external_event_id", "payment__merchant_reference"]
    autocomplete_fields = ["provider", "payment"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
