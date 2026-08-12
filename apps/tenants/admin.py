from django.contrib import admin

from apps.tenants.models import Tenant, TenantMembership


class TenantMembershipInline(admin.TabularInline):
    model = TenantMembership
    extra = 0
    autocomplete_fields = ["user", "invited_by"]


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "sector", "status", "default_currency", "created_at"]
    list_filter = ["status", "sector"]
    search_fields = ["name", "contact_email", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TenantMembershipInline]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "role", "is_active", "created_at"]
    list_filter = ["role", "is_active"]
    search_fields = ["user__email", "tenant__name"]
    autocomplete_fields = ["user", "tenant", "invited_by"]
