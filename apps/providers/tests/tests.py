from decimal import Decimal

import pytest

from apps.providers.base import ProviderOutcome, ProviderTimeoutError
from apps.providers.mock import MockPaymentProviderAdapter, build_mock_callback_payload


@pytest.mark.django_db
class TestMockAdapter:
    def test_default_outcome_is_successful(self):
        adapter = MockPaymentProviderAdapter()
        result = adapter.initiate_payment(
            amount=Decimal("1000"), currency="TZS", control_number="260812000123",
            payer_reference="", merchant_reference="REF-1", metadata={},
        )
        assert result.outcome == ProviderOutcome.SUCCESSFUL
        assert result.provider_reference

    def test_failed_outcome_can_be_simulated(self):
        adapter = MockPaymentProviderAdapter()
        result = adapter.initiate_payment(
            amount=Decimal("1000"), currency="TZS", control_number="260812000123",
            payer_reference="", merchant_reference="REF-2", metadata={"mock_outcome": "failed"},
        )
        assert result.outcome == ProviderOutcome.FAILED

    def test_timeout_raises_but_still_records_what_actually_happened(self):
        """The core honesty of the mock: a timeout doesn't mean nothing
        happened at the provider — it means we didn't hear back. The mock
        deterministically records SUCCESSFUL server-side even though the
        caller only sees a timeout exception."""
        adapter = MockPaymentProviderAdapter()
        with pytest.raises(ProviderTimeoutError):
            adapter.initiate_payment(
                amount=Decimal("1000"), currency="TZS", control_number="260812000123",
                payer_reference="", merchant_reference="REF-3", metadata={"mock_outcome": "timeout"},
            )
        result = adapter.query_payment(merchant_reference="REF-3")
        assert result.outcome == ProviderOutcome.SUCCESSFUL

    def test_query_unknown_reference_returns_unknown(self):
        adapter = MockPaymentProviderAdapter()
        result = adapter.query_payment(merchant_reference="NEVER-INITIATED")
        assert result.outcome == ProviderOutcome.UNKNOWN

    def test_validate_reference(self):
        adapter = MockPaymentProviderAdapter()
        assert adapter.validate_reference(control_number="260812000123") is True
        assert adapter.validate_reference(control_number="not-numeric") is False

    def test_health_check(self):
        assert MockPaymentProviderAdapter().health_check() is True


@pytest.mark.django_db
class TestMockCallbackSignature:
    def test_correctly_signed_callback_is_accepted(self):
        adapter = MockPaymentProviderAdapter()
        body, headers = build_mock_callback_payload(
            event_id="evt-1", provider_reference="MOCK-ABC", outcome=ProviderOutcome.SUCCESSFUL
        )
        parsed = adapter.process_callback(raw_payload=body, headers=headers)
        assert parsed.external_event_id == "evt-1"
        assert parsed.outcome == ProviderOutcome.SUCCESSFUL

    def test_tampered_payload_is_rejected(self):
        from apps.providers.base import InvalidCallbackSignatureError

        adapter = MockPaymentProviderAdapter()
        body, headers = build_mock_callback_payload(
            event_id="evt-2", provider_reference="MOCK-XYZ", outcome=ProviderOutcome.SUCCESSFUL
        )
        tampered_body = body.replace(b"successful", b"failed")  # any change invalidates the signature
        with pytest.raises(InvalidCallbackSignatureError):
            adapter.process_callback(raw_payload=tampered_body, headers=headers)

    def test_missing_signature_is_rejected(self):
        from apps.providers.base import InvalidCallbackSignatureError

        adapter = MockPaymentProviderAdapter()
        body, _headers = build_mock_callback_payload(
            event_id="evt-3", provider_reference="MOCK-QQQ", outcome=ProviderOutcome.SUCCESSFUL
        )
        with pytest.raises(InvalidCallbackSignatureError):
            adapter.process_callback(raw_payload=body, headers={})
