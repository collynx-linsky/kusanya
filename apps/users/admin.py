from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.core.encrypted_fields import EncryptedFieldSearchAdminMixin
from apps.users.models import PlatformMembership, User


@admin.register(User)
class UserAdmin(EncryptedFieldSearchAdminMixin, DjangoUserAdmin):
    """first_name/last_name are encrypted at rest (ADR-032) — search on
    them is exact-match only via their lookup_hash companions, not the
    substring match `search_fields` normally gives. `email` is not
    encrypted (see User's docstring) and keeps normal substring search."""

    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "is_staff", "is_active"]
    search_fields = ["email"]
    encrypted_exact_search_fields = ["first_name", "last_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone_number")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


@admin.register(PlatformMembership)
class PlatformMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "role", "is_active", "created_at"]
    list_filter = ["role", "is_active"]
    search_fields = ["user__email"]
    autocomplete_fields = ["user"]
