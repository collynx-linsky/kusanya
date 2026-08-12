from django.contrib import admin

from apps.webhooks.models import WebhookDelivery, WebhookEndpoint


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ["url", "tenant", "is_active", "description"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["url", "description"]
    autocomplete_fields = ["tenant"]
    readonly_fields = ["secret"]


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ["event_type", "endpoint", "status", "attempt_count", "response_status_code", "created_at"]
    list_filter = ["status", "event_type", "tenant"]
    search_fields = ["endpoint__url", "correlation_id"]
    autocomplete_fields = ["tenant", "endpoint"]
    readonly_fields = ["payload", "attempt_count", "last_attempted_at", "response_status_code", "response_body"]
