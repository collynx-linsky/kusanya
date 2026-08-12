"""
MOCK / SANDBOX payment provider adapter.

This is the ONLY provider adapter that exists in this codebase (build
spec section 43: no invented real provider APIs, no fabricated
credentials). Every place it's used must be unmistakably labeled as
mock/sandbox — see `PaymentProvider.is_sandbox` and the "SANDBOX" suffix
in `PaymentProvider.__str__`, and never let a mock payment be presented
to a user as a real one (build spec section 44).

Outcome is controlled by `metadata["mock_outcome"]` passed into
`initiate_payment()`: "successful" (default), "failed", "pending", or
"timeout". "timeout" specifically simulates the realistic scenario a real
integration must handle: the provider actually processed the request
(deterministically, here: as SUCCESSFUL) but the response never reached
KUSANYA — proving the "never assume timeout == failure, always query
before deciding" rule in docs/PAYMENT_LIFECYCLE.md is enforceable against
something, not just documented.
"""

import json
import uuid
from decimal import Decimal

from apps.core.signing import sign, verify
from apps.providers.base import (
    InvalidCallbackSignatureError,
    PaymentProviderAdapter,
    ProviderCallbackResult,
    ProviderError,
    ProviderOutcome,
    ProviderResult,
    ProviderTimeoutError,
)
from apps.providers.models import MockProviderTransaction

DEFAULT_CALLBACK_SECRET = "mock-provider-callback-secret"  # sandbox only — never a real secret


class MockPaymentProviderAdapter(PaymentProviderAdapter):
    def __init__(self, callback_secret: str = DEFAULT_CALLBACK_SECRET):
        self.callback_secret = callback_secret

    def initiate_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        control_number: str,
        payer_reference: str,
        merchant_reference: str,
        metadata: dict,
    ) -> ProviderResult:
        outcome_hint = (metadata or {}).get("mock_outcome", "successful")
        provider_reference = f"MOCK-{uuid.uuid4().hex[:10].upper()}"

        # What actually "happens" at the (simulated) provider — a timeout
        # doesn't mean nothing happened, it means we didn't hear back.
        actual_outcome = {
            "successful": ProviderOutcome.SUCCESSFUL,
            "failed": ProviderOutcome.FAILED,
            "pending": ProviderOutcome.PENDING,
            "timeout": ProviderOutcome.SUCCESSFUL,
        }.get(outcome_hint, ProviderOutcome.SUCCESSFUL)

        MockProviderTransaction.objects.create(
            merchant_reference=merchant_reference,
            provider_reference=provider_reference,
            outcome=actual_outcome.value,
        )

        if outcome_hint == "timeout":
            raise ProviderTimeoutError(
                f"Simulated provider timeout for merchant_reference={merchant_reference}"
            )

        return ProviderResult(
            outcome=actual_outcome,
            provider_reference=provider_reference,
            message="Simulated by the MOCK/SANDBOX provider — no real payment occurred.",
            raw_response={"mock": True, "merchant_reference": merchant_reference},
        )

    def query_payment(self, *, merchant_reference: str) -> ProviderResult:
        txn = MockProviderTransaction.objects.filter(merchant_reference=merchant_reference).first()
        if txn is None:
            return ProviderResult(
                outcome=ProviderOutcome.UNKNOWN,
                message="No record found at the provider for this reference yet.",
            )
        return ProviderResult(
            outcome=ProviderOutcome(txn.outcome),
            provider_reference=txn.provider_reference,
            raw_response={"mock": True},
        )

    def validate_reference(self, *, control_number: str) -> bool:
        return bool(control_number) and control_number.isdigit()

    def process_callback(self, *, raw_payload: bytes, headers: dict) -> ProviderCallbackResult:
        signature = headers.get("X-Mock-Signature", "")
        body_text = raw_payload.decode("utf-8")
        if not verify(self.callback_secret, body_text, signature):
            raise InvalidCallbackSignatureError("Mock provider callback signature did not verify.")

        try:
            data = json.loads(body_text)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(f"Malformed mock callback payload: {exc}") from exc

        return ProviderCallbackResult(
            external_event_id=data["event_id"],
            provider_reference=data["provider_reference"],
            outcome=ProviderOutcome(data["outcome"]),
            raw_response=data,
        )

    def refund(self, *, provider_reference: str, amount: Decimal) -> ProviderResult:
        return ProviderResult(
            outcome=ProviderOutcome.SUCCESSFUL,
            provider_reference=provider_reference,
            message="Simulated refund — MOCK/SANDBOX provider.",
            raw_response={"mock": True, "refunded_amount": str(amount)},
        )

    def reverse(self, *, provider_reference: str) -> ProviderResult:
        return ProviderResult(
            outcome=ProviderOutcome.SUCCESSFUL,
            provider_reference=provider_reference,
            message="Simulated reversal — MOCK/SANDBOX provider.",
            raw_response={"mock": True},
        )

    def reconcile(self, *, provider_reference: str) -> ProviderResult:
        txn = MockProviderTransaction.objects.filter(provider_reference=provider_reference).first()
        if txn is None:
            return ProviderResult(outcome=ProviderOutcome.UNKNOWN, message="Unknown to mock provider.")
        return ProviderResult(outcome=ProviderOutcome(txn.outcome), provider_reference=provider_reference)

    def health_check(self) -> bool:
        return True


def build_mock_callback_payload(
    *, event_id: str, provider_reference: str, outcome: ProviderOutcome, secret: str = DEFAULT_CALLBACK_SECRET
) -> tuple[bytes, dict]:
    """Test/demo helper: builds a correctly-signed mock callback the way
    the (simulated) provider would send it, so tests and the manual
    "simulate provider callback" portal action don't hand-roll signing
    logic in three different places."""
    body = json.dumps(
        {"event_id": event_id, "provider_reference": provider_reference, "outcome": outcome.value}
    ).encode("utf-8")
    signature = sign(secret, body.decode("utf-8"))
    return body, {"X-Mock-Signature": signature}
