from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only by design — audit records are immutable (see models.py)."""

    list_display = ["created_at", "action", "actor_label", "tenant", "correlation_id"]
    list_filter = ["action", "tenant"]
    search_fields = ["action", "actor_label", "correlation_id", "object_id"]
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
