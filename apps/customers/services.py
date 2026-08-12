"""
Idempotent creation for customers and accounts — build spec section 14:
an ERP retrying a "create customer"/"create account" call with the same
`external_reference` must get back the existing record, never a
duplicate.
"""

from django.db import transaction

from apps.audit.services import record_audit_event
from apps.customers.models import Customer, CustomerAccount


def get_or_create_customer(*, tenant, full_name, external_reference="", actor=None, **fields):
    if external_reference:
        existing = Customer.objects.filter(
            tenant=tenant, external_reference=external_reference
        ).first()
        if existing is not None:
            return existing, False

    with transaction.atomic():
        customer = Customer.objects.create(
            tenant=tenant,
            full_name=full_name,
            external_reference=external_reference,
            **fields,
        )
        record_audit_event(
            action="customer.created", actor=actor, tenant=tenant, target=customer
        )
    return customer, True


def get_or_create_customer_account(
    *, tenant, customer, name, external_reference="", actor=None, **fields
):
    if external_reference:
        existing = CustomerAccount.objects.filter(
            tenant=tenant, external_reference=external_reference
        ).first()
        if existing is not None:
            return existing, False

    with transaction.atomic():
        account = CustomerAccount.objects.create(
            tenant=tenant,
            customer=customer,
            name=name,
            external_reference=external_reference,
            **fields,
        )
        record_audit_event(
            action="customer_account.created", actor=actor, tenant=tenant, target=account
        )
    return account, True
