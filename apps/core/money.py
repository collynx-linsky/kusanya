"""
Money handling helpers.

RULE: money is never represented as float, anywhere in KUSANYA — not in
models, not in serializers, not in provider adapters, not in reports. All
monetary values are `decimal.Decimal`, stored as DecimalField, and always
carry an explicit currency code. See docs/DATABASE_ARCHITECTURE.md.
"""

from decimal import ROUND_HALF_UP, Decimal

# Default currency for tenants that don't configure one explicitly.
# Multi-currency is a first-class concept (see Tenant.default_currency /
# future CollectionAccount.currency) — this is only the platform default.
DEFAULT_CURRENCY = "TZS"

# Minor-unit exponent per currency, used for rounding. TZS has no minor
# unit in everyday circulation but is still tracked to 2dp internally for
# arithmetic safety; extend this map as new currencies are supported.
CURRENCY_EXPONENTS = {
    "TZS": 2,
    "KES": 2,
    "UGX": 0,
    "USD": 2,
}


def quantize(amount: Decimal, currency: str = DEFAULT_CURRENCY) -> Decimal:
    """Round `amount` to the correct number of decimal places for `currency`."""
    exponent = CURRENCY_EXPONENTS.get(currency, 2)
    quantum = Decimal("1").scaleb(-exponent)
    return Decimal(amount).quantize(quantum, rounding=ROUND_HALF_UP)


def money_field_kwargs(**overrides) -> dict:
    """Standard kwargs for a DecimalField representing money.

    Use as: `amount = models.DecimalField(**money_field_kwargs())`
    Keeps precision/decimal_places consistent across every model that
    stores currency amounts instead of each app picking its own.
    """
    kwargs = {"max_digits": 18, "decimal_places": 2}
    kwargs.update(overrides)
    return kwargs
