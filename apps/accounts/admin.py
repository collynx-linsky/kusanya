from django.contrib import admin

from apps.accounts.models import BackupCode, MFADevice


@admin.register(MFADevice)
class MFADeviceAdmin(admin.ModelAdmin):
    """Read-only, and deliberately never displays the raw TOTP secret —
    platform staff can see *that* a user has MFA enabled for support
    purposes, never the secret itself (that would defeat the point)."""

    list_display = ["user", "confirmed", "last_used_at", "created_at"]
    list_filter = ["confirmed"]
    search_fields = ["user__email"]
    autocomplete_fields = ["user"]
    readonly_fields = ["user", "confirmed", "last_used_at", "created_at", "secret_redacted"]
    exclude = ["secret"]

    def secret_redacted(self, obj):
        return "•" * 16

    secret_redacted.short_description = "Secret"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(BackupCode)
class BackupCodeAdmin(admin.ModelAdmin):
    """Read-only — shows only whether a code has been used, never the
    code itself (only a hash is stored, same as passwords/API secrets)."""

    list_display = ["user", "used_at", "created_at"]
    list_filter = ["used_at"]
    search_fields = ["user__email"]
    autocomplete_fields = ["user"]
    readonly_fields = ["user", "used_at", "created_at"]
    exclude = ["lookup_hash"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
