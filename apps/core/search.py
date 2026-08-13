"""Backs the command palette (docs/DESIGN_SYSTEM.md's "Command palette"
section) — real search against real records, reusing the exact-match
constraint already established for encrypted fields (ADR-032), not a
separate search index or fabricated result set."""

from apps.core.encrypted_fields import compute_lookup_hash


def search_customers(tenant, query: str, *, limit: int = 5):
    from apps.customers.models import Customer

    if not query:
        return []
    matches = Customer.objects.filter(tenant=tenant, full_name_lookup_hash=compute_lookup_hash(query))
    matches = matches or Customer.objects.filter(
        tenant=tenant, external_reference__icontains=query
    )
    return list(matches[:limit])


def search_bills(tenant, query: str, *, limit: int = 5):
    from django.db.models import Q

    from apps.billing.models import Bill

    if not query:
        return []
    return list(
        Bill.objects.filter(tenant=tenant)
        .filter(Q(bill_number__icontains=query) | Q(external_reference__icontains=query))
        .select_related("customer_account")[:limit]
    )
