from decimal import Decimal

import pytest

from apps.ledger.models import LedgerAccount, LedgerEntry, LedgerEntryImmutableError, LedgerEntryType
from apps.ledger.services import post_compensating_entry, post_entry


@pytest.mark.django_db
class TestLedgerImmutability:
    def test_cannot_modify_an_existing_entry(self, make_tenant):
        tenant = make_tenant()
        entry = post_entry(
            tenant=tenant, entry_type=LedgerEntryType.ADJUSTMENT, account=LedgerAccount.PLATFORM,
            amount=Decimal("100"),
        )
        entry.amount = Decimal("999")
        with pytest.raises(LedgerEntryImmutableError):
            entry.save()

    def test_cannot_delete_an_entry(self, make_tenant):
        tenant = make_tenant()
        entry = post_entry(
            tenant=tenant, entry_type=LedgerEntryType.ADJUSTMENT, account=LedgerAccount.PLATFORM,
            amount=Decimal("100"),
        )
        with pytest.raises(LedgerEntryImmutableError):
            entry.delete()

    def test_correction_is_a_compensating_entry_not_a_mutation(self, make_tenant):
        tenant = make_tenant()
        original = post_entry(
            tenant=tenant, entry_type=LedgerEntryType.PLATFORM_PAYMENT_FEE, account=LedgerAccount.PLATFORM,
            amount=Decimal("50"), reference="PAY-1",
        )
        compensating = post_compensating_entry(
            original=original, entry_type=LedgerEntryType.REFUND, amount=Decimal("-50")
        )

        original.refresh_from_db()
        assert original.amount == Decimal("50.00")  # untouched
        assert compensating.related_entry_id == original.id
        assert compensating.amount == Decimal("-50.00")
        assert LedgerEntry.objects.filter(tenant=tenant).count() == 2
