from django.contrib import admin

from apps.api.models import ApiCredential


@admin.register(ApiCredential)
class ApiCredentialAdmin(admin.ModelAdmin):
    list_display = ["name", "key_id", "tenant", "is_active", "last_used_at", "created_at"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["name", "key_id", "tenant__name"]
    autocomplete_fields = ["tenant", "created_by"]
    readonly_fields = ["key_id", "secret_hash", "last_used_at", "created_at"]
