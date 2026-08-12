from django.contrib import admin

from apps.notifications.models import Notification, NotificationTemplate


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ["tenant", "event_type", "channel", "is_active"]
    list_filter = ["event_type", "channel", "is_active"]
    search_fields = ["tenant__name"]
    autocomplete_fields = ["tenant"]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Read-only — a notification is a delivery record, not editable data."""

    list_display = ["created_at", "tenant", "event_type", "channel", "recipient", "status"]
    list_filter = ["status", "channel", "event_type", "tenant"]
    search_fields = ["recipient", "correlation_id"]
    autocomplete_fields = ["tenant"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
