"""
The one place provider-code-to-adapter-class wiring is allowed to exist.
The orchestrator (apps.payments.services) never imports a specific
adapter class directly — it asks this registry for one, keyed by the
`PaymentProvider.code` on the `Payment` row. This is the seam build spec
section 12 requires ("do not hard-code a particular provider into the
billing engine") — everything on the other side of `get_adapter()` only
ever sees the `PaymentProviderAdapter` interface.
"""

from apps.providers.base import PaymentProviderAdapter, ProviderError
from apps.providers.mock import MockPaymentProviderAdapter

_ADAPTER_CLASSES: dict[str, type[PaymentProviderAdapter]] = {
    "mock": MockPaymentProviderAdapter,
}


def get_adapter(provider) -> PaymentProviderAdapter:
    """`provider` is an `apps.providers.models.PaymentProvider` instance."""
    adapter_class = _ADAPTER_CLASSES.get(provider.code)
    if adapter_class is None:
        raise ProviderError(
            f"No adapter registered for provider code '{provider.code}'. "
            "Real provider adapters are only added once official API "
            "documentation and credentials exist for that provider — see "
            "docs/PAYMENT_PROVIDER_ARCHITECTURE.md."
        )
    return adapter_class()
