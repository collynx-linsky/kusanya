from django.contrib import admin

from apps.customers.models import Customer, CustomerAccount


class CustomerAccountInline(admin.TabularInline):
    model = CustomerAccount
    extra = 0
    fields = ["name", "revenue_source", "external_reference", "is_active"]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["full_name", "tenant", "email", "phone_number", "is_active"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["full_name", "email", "phone_number", "external_reference"]
    autocomplete_fields = ["tenant"]
    inlines = [CustomerAccountInline]


@admin.register(CustomerAccount)
class CustomerAccountAdmin(admin.ModelAdmin):
    list_display = ["name", "customer", "tenant", "revenue_source", "is_active"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["name", "customer__full_name", "external_reference"]
    autocomplete_fields = ["tenant", "customer", "revenue_source"]
