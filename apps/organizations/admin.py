from django.contrib import admin

from apps.organizations.models import Branch, Department


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "code", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "tenant__name"]
    autocomplete_fields = ["tenant"]


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "branch", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "tenant__name"]
    autocomplete_fields = ["tenant", "branch"]
