import pytest

from apps.audit.models import AuditLog, AuditLogImmutableError
from apps.audit.services import record_audit_event


@pytest.mark.django_db
class TestAuditLogChain:
    def test_first_record_chains_from_genesis(self):
        event = record_audit_event(action="test.first")
        assert event.previous_hash == "0" * 64

    def test_each_record_chains_to_the_previous_hash(self):
        first = record_audit_event(action="test.one")
        second = record_audit_event(action="test.two")
        assert second.previous_hash == first.record_hash

    def test_chain_verifies_intact_after_normal_writes(self, make_user):
        user = make_user()
        record_audit_event(action="test.a", actor=user)
        record_audit_event(action="test.b", actor=user)
        record_audit_event(action="test.c")

        intact, broken_at = AuditLog.verify_chain()
        assert intact is True
        assert broken_at is None

    def test_cannot_modify_an_existing_audit_record(self):
        event = record_audit_event(action="test.immutable")
        event.action = "tampered"
        with pytest.raises(AuditLogImmutableError):
            event.save()

    def test_cannot_delete_an_audit_record(self):
        event = record_audit_event(action="test.no_delete")
        with pytest.raises(AuditLogImmutableError):
            event.delete()

    def test_chain_stays_verifiable_after_the_actor_is_deleted(self, make_user):
        """Regression test for ARCHITECTURE_DECISIONS ADR-035: found
        live via apps.audit.views.verify_chain -- deleting a user who
        performed an audited action used to break chain verification
        for their historical records, because the hash was computed
        over the mutable `actor_id` FK (on_delete=SET_NULL nulls it on
        deletion) instead of the immutable `actor_label` snapshot."""
        user = make_user(email="deleted-actor@example.com")
        record_audit_event(action="test.before_actor_deleted", actor=user)

        user.delete()

        intact, broken_at = AuditLog.verify_chain()
        assert intact is True
        assert broken_at is None

    def test_hash_is_computed_over_actor_label_not_actor_id(self, make_user):
        """The specific mechanism behind the regression test above --
        confirms the payload uses the stable label, not the live FK."""
        user = make_user(email="label-check@example.com")
        event = record_audit_event(action="test.label_hash", actor=user)

        assert '"actor_label": "' + str(user) + '"' in event._canonical_payload()
        assert "actor_id" not in event._canonical_payload()

    def test_login_success_is_audited(self, client, make_user):
        user = make_user(email="login-test@example.com", password="Str0ngPassw0rd!")
        before = AuditLog.objects.filter(action="auth.login").count()

        client.login(username="login-test@example.com", password="Str0ngPassw0rd!")

        after = AuditLog.objects.filter(action="auth.login").count()
        assert after == before + 1

    def test_failed_login_is_audited(self, client, make_user):
        make_user(email="failed-login@example.com", password="Str0ngPassw0rd!")
        before = AuditLog.objects.filter(action="auth.login_failed").count()

        client.login(username="failed-login@example.com", password="WrongPassword!")

        after = AuditLog.objects.filter(action="auth.login_failed").count()
        assert after == before + 1


@pytest.mark.django_db
class TestGetActivityFor:
    """apps.audit.services.get_activity_for -- backs the activity
    timeline component (docs/DESIGN_SYSTEM.md)."""

    def test_returns_only_events_for_the_given_object_newest_first(self, make_tenant, make_customer):
        from apps.audit.services import get_activity_for

        tenant = make_tenant()
        customer_a = make_customer(tenant, full_name="Amina")
        customer_b = make_customer(tenant, full_name="Bahati")

        record_audit_event(action="customer.created", target=customer_a)
        record_audit_event(action="customer.updated", target=customer_a)
        record_audit_event(action="customer.created", target=customer_b)

        activity = list(get_activity_for(customer_a))

        assert [e.action for e in activity] == ["customer.updated", "customer.created"]

    def test_respects_the_limit(self, make_tenant, make_customer):
        from apps.audit.services import get_activity_for

        tenant = make_tenant()
        customer = make_customer(tenant)
        for i in range(5):
            record_audit_event(action=f"test.event.{i}", target=customer)

        activity = list(get_activity_for(customer, limit=2))

        assert len(activity) == 2


@pytest.mark.django_db
class TestVerifyChainView:
    """apps.audit.views.verify_chain -- platform-staff-only, since the
    hash chain is a single global sequence, not one per tenant (see the
    module's own docstring and ARCHITECTURE_DECISIONS ADR-006)."""

    def test_non_platform_staff_cannot_access_it(self, client, make_user, make_tenant, make_membership):
        tenant = make_tenant()
        user = make_user(email="notstaff@example.com")
        make_membership(user, tenant)
        client.force_login(user)

        response = client.post("/audit/platform/verify-chain/")

        assert response.status_code == 403

    def test_platform_staff_gets_a_success_message_when_chain_is_intact(
        self, client, make_user, make_platform_role
    ):
        from apps.users.models import PlatformRole

        user = make_user(email="auditor@example.com")
        user.is_staff = True
        user.save()
        make_platform_role(user, role=PlatformRole.AUDITOR)
        client.force_login(user)

        response = client.post("/audit/platform/verify-chain/", follow=True)

        messages = list(response.context["messages"])
        assert any("verified" in str(m).lower() for m in messages)
