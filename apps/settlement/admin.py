from django.contrib import admin

from apps.settlement.models import SettlementBatch


@admin.register(SettlementBatch)
class SettlementBatchAdmin(admin.ModelAdmin):
    list_display = ["reference", "tenant", "provider", "status", "gross_amount", "net_amount", "currency", "period_end"]
    list_filter = ["status", "provider", "tenant"]
    search_fields = ["reference", "external_settlement_reference"]
    autocomplete_fields = ["tenant", "provider"]
    readonly_fields = ["reference", "gross_amount", "platform_fee_total", "provider_fee_total", "net_amount"]
