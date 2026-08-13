from django.contrib import admin

from apps.core.encrypted_fields import EncryptedFieldSearchAdminMixin
from apps.customers.models import Customer, CustomerAccount


class CustomerAccountInline(admin.TabularInline):
    model = CustomerAccount
    extra = 0
    fields = ["name", "revenue_source", "external_reference", "is_active"]


@admin.register(Customer)
class CustomerAdmin(EncryptedFieldSearchAdminMixin, admin.ModelAdmin):
    """full_name/email/phone_number are encrypted at rest (ADR-032) —
    search on them is exact-match only via their lookup_hash companions,
    not the substring match `search_fields` normally gives. Typing a
    customer's complete name/email/phone finds them; typing part of one
    does not."""

    list_display = ["full_name", "tenant", "email", "phone_number", "is_active"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["external_reference"]
    encrypted_exact_search_fields = ["full_name", "email", "phone_number"]
    autocomplete_fields = ["tenant"]
    inlines = [CustomerAccountInline]


@admin.register(CustomerAccount)
class CustomerAccountAdmin(admin.ModelAdmin):
    list_display = ["name", "customer", "tenant", "revenue_source", "is_active"]
    list_filter = ["is_active", "tenant"]
    # Not customer__full_name — that's encrypted now (ADR-032); find the
    # account via CustomerAdmin's exact-match search or this account's
    # own name/external_reference instead.
    search_fields = ["name", "external_reference"]
    autocomplete_fields = ["tenant", "customer", "revenue_source"]
