from django.contrib import admin

from apps.providers.models import MockProviderTransaction, PaymentChannel, PaymentProvider


class PaymentChannelInline(admin.TabularInline):
    model = PaymentChannel
    extra = 0


@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "is_sandbox", "is_active"]
    list_filter = ["is_sandbox", "is_active"]
    search_fields = ["name", "code"]
    inlines = [PaymentChannelInline]


@admin.register(PaymentChannel)
class PaymentChannelAdmin(admin.ModelAdmin):
    list_display = ["name", "provider", "channel_type", "is_active"]
    list_filter = ["channel_type", "is_active"]
    search_fields = ["name", "code"]
    autocomplete_fields = ["provider"]


@admin.register(MockProviderTransaction)
class MockProviderTransactionAdmin(admin.ModelAdmin):
    """Read-only view into the mock provider's simulated internal state —
    useful for debugging test payments, not a real financial record."""

    list_display = ["merchant_reference", "provider_reference", "outcome", "created_at"]
    search_fields = ["merchant_reference", "provider_reference"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
