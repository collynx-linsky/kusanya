"""
Platform-level catalog of payment providers/channels. Deliberately NOT
tenant-scoped — the catalog of "which providers KUSANYA integrates with"
is a platform decision; which tenants are *permitted* to use a given
provider is a Phase 4 concern (a CollectionAccount/settlement-adjacent
concept — see docs/PAYMENT_PROVIDER_ARCHITECTURE.md's note on scope) not
modeled yet in Phase 3.

Only one provider exists in this codebase: "mock" — a clearly-labeled
sandbox adapter (see apps/providers/mock.py and build spec section 43:
no invented real provider APIs).
"""

from django.db import models

from apps.core.models import BaseModel


class PaymentProvider(BaseModel):
    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=150)
    is_sandbox = models.BooleanField(
        default=True,
        help_text="True for mock/sandbox providers. Must never be silently "
        "presented to a user as a real payment method.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        label = " (SANDBOX)" if self.is_sandbox else ""
        return f"{self.name}{label}"


class PaymentChannelType(models.TextChoices):
    MOBILE_MONEY = "mobile_money", "Mobile money"
    BANK = "bank", "Bank"
    CARD = "card", "Card"
    OTHER = "other", "Other"


class PaymentChannel(BaseModel):
    provider = models.ForeignKey(PaymentProvider, on_delete=models.CASCADE, related_name="channels")
    code = models.SlugField(max_length=32)
    name = models.CharField(max_length=150)
    channel_type = models.CharField(max_length=16, choices=PaymentChannelType.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["provider__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "code"], name="unique_channel_code_per_provider")
        ]

    def __str__(self):
        return f"{self.name} ({self.provider.name})"


class MockProviderTransaction(BaseModel):
    """Used ONLY by apps.providers.mock.MockPaymentProviderAdapter to
    simulate a real provider's own transaction store — a real adapter
    would have no equivalent model here at all; it would call out to the
    actual provider's API. Exists so `query_payment()` can be answered
    correctly (by our own merchant_reference) even across process
    boundaries (web vs. Celery worker) and even for a payment whose
    initiate response was "lost" (simulated timeout) — see
    apps/providers/mock.py.
    """

    merchant_reference = models.CharField(max_length=64, unique=True)
    provider_reference = models.CharField(max_length=64)
    outcome = models.CharField(max_length=16)

    def __str__(self):
        return f"MOCK {self.merchant_reference} -> {self.outcome}"
