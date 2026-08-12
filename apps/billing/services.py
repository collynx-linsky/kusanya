"""
Idempotent bill creation. See docs/BILLING_SPEC.md and build spec section
14's `external_reference` / `INV-2026-00125` example: retrying a "create
bill" call with the same external_reference must return the existing
bill, never create a duplicate.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.audit.services import record_audit_event
from apps.billing.models import Bill, BillItem


def get_or_create_bill(
    *,
    tenant,
    customer_account,
    items: list[dict],
    revenue_source=None,
    external_reference="",
    due_date=None,
    metadata=None,
    actor=None,
):
    """`items` is a list of {"description": str, "quantity": Decimal, "unit_amount": Decimal}.

    Returns (bill, created). If `external_reference` matches an existing
    bill for this tenant, that bill is returned unchanged — its items are
    NOT re-created or updated, matching the idempotency contract: this is
    "did you already do this," not "upsert."
    """
    if external_reference:
        existing = Bill.objects.filter(
            tenant=tenant, external_reference=external_reference
        ).first()
        if existing is not None:
            return existing, False

    # bill_number collisions are astronomically unlikely (date prefix +
    # 8 hex chars of a uuid4) but the DB constraint is the real guarantee
    # — retry generation on the rare IntegrityError rather than trusting
    # uniqueness by construction alone.
    for _attempt in range(3):
        try:
            with transaction.atomic():
                bill = Bill.objects.create(
                    tenant=tenant,
                    customer_account=customer_account,
                    revenue_source=revenue_source,
                    external_reference=external_reference,
                    due_date=due_date,
                    metadata=metadata or {},
                )
                BillItem.objects.bulk_create(
                    [
                        BillItem(
                            tenant=tenant,
                            bill=bill,
                            description=item["description"],
                            quantity=Decimal(str(item.get("quantity", 1))),
                            unit_amount=Decimal(str(item["unit_amount"])),
                            line_total=Decimal(str(item.get("quantity", 1)))
                            * Decimal(str(item["unit_amount"])),
                        )
                        for item in items
                    ]
                )
                bill.recalculate_total()
                record_audit_event(
                    action="bill.created",
                    actor=actor,
                    tenant=tenant,
                    target=bill,
                    after={"total_amount": str(bill.total_amount), "status": bill.status},
                )
                _dispatch_bill_event(bill, "bill.created")
            return bill, True
        except IntegrityError:
            # Could be a bill_number collision (retry generation) or a
            # concurrent request that won the race on external_reference
            # (in which case the idempotent thing to do is return what
            # that other request created, not fail).
            if external_reference:
                existing = Bill.objects.filter(
                    tenant=tenant, external_reference=external_reference
                ).first()
                if existing is not None:
                    return existing, False
            continue

    raise IntegrityError("Could not generate a unique bill number after 3 attempts.")


def cancel_bill(bill: Bill, *, actor=None):
    from apps.billing.models import BillStatus

    bill.transition_to(BillStatus.CANCELLED)
    record_audit_event(action="bill.cancelled", actor=actor, tenant=bill.tenant, target=bill)
    _dispatch_bill_event(bill, "bill.cancelled")
    return bill


def _dispatch_bill_event(bill: Bill, event_type: str) -> None:
    from apps.webhooks.services import dispatch_event

    dispatch_event(
        tenant=bill.tenant,
        event_type=event_type,
        payload={
            "bill_id": str(bill.id),
            "bill_number": bill.bill_number,
            "status": bill.status,
            "total_amount": str(bill.total_amount),
            "currency": bill.currency,
            "customer_account": bill.customer_account.name,
        },
    )
