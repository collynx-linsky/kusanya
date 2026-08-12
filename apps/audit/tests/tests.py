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
