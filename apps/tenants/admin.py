from django.contrib import admin

from apps.core.encrypted_fields import EncryptedFieldSearchAdminMixin
from apps.tenants.models import Tenant, TenantMembership


class TenantMembershipInline(admin.TabularInline):
    model = TenantMembership
    extra = 0
    autocomplete_fields = ["user", "invited_by"]


@admin.register(Tenant)
class TenantAdmin(EncryptedFieldSearchAdminMixin, admin.ModelAdmin):
    """contact_email is encrypted at rest (ADR-032) — search on it is
    exact-match only via its lookup_hash companion."""

    list_display = ["name", "sector", "status", "default_currency", "created_at"]
    list_filter = ["status", "sector"]
    search_fields = ["name", "slug"]
    encrypted_exact_search_fields = ["contact_email"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TenantMembershipInline]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "role", "is_active", "created_at"]
    list_filter = ["role", "is_active"]
    search_fields = ["user__email", "tenant__name"]
    autocomplete_fields = ["user", "tenant", "invited_by"]
