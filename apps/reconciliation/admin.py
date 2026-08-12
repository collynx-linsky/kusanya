from django.contrib import admin

from apps.reconciliation.models import ReconciliationException, ReconciliationRun


class ReconciliationExceptionInline(admin.TabularInline):
    model = ReconciliationException
    extra = 0
    fields = ["payment", "exception_type", "status"]
    readonly_fields = ["payment", "exception_type", "status"]


@admin.register(ReconciliationRun)
class ReconciliationRunAdmin(admin.ModelAdmin):
    list_display = ["id", "tenant", "status", "total_checked", "matched_count", "exception_count", "started_at"]
    list_filter = ["status", "tenant"]
    search_fields = ["id", "tenant__name"]
    autocomplete_fields = ["tenant", "triggered_by"]
    inlines = [ReconciliationExceptionInline]


@admin.register(ReconciliationException)
class ReconciliationExceptionAdmin(admin.ModelAdmin):
    list_display = ["payment", "exception_type", "status", "tenant", "created_at"]
    list_filter = ["exception_type", "status", "tenant"]
    search_fields = ["payment__merchant_reference"]
    autocomplete_fields = ["tenant", "payment", "run", "resolved_by"]
