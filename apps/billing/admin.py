from django.contrib import admin

from apps.billing.models import Bill, BillItem, RevenueSource


class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 0
    readonly_fields = ["line_total"]


@admin.register(RevenueSource)
class RevenueSourceAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "code", "is_active"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["name", "code"]
    autocomplete_fields = ["tenant"]


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ["bill_number", "tenant", "customer_account", "status", "total_amount", "currency"]
    list_filter = ["status", "tenant"]
    search_fields = ["bill_number", "external_reference", "customer_account__name"]
    autocomplete_fields = ["tenant", "customer_account", "revenue_source"]
    readonly_fields = ["bill_number", "total_amount"]
    inlines = [BillItemInline]
