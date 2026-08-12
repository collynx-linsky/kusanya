from django import forms


class PayBillForm(forms.Form):
    """Portal payment-initiation form. `mock_outcome` only exists because
    the only provider wired up is the mock/sandbox one (see
    apps/providers/mock.py) — it lets a developer/tester deliberately
    exercise each branch of the payment lifecycle (success, failure,
    pending, and the timeout -> UNKNOWN path) without needing a real
    provider. A real provider adapter would never expose this."""

    MOCK_OUTCOME_CHOICES = [
        ("successful", "Successful"),
        ("failed", "Failed"),
        ("pending", "Pending"),
        ("timeout", "Timeout (provider response lost — becomes UNKNOWN)"),
    ]

    amount = forms.DecimalField(max_digits=18, decimal_places=2, min_value=0.01)
    payer_reference = forms.CharField(max_length=100, required=False, label="Payer phone/reference")
    mock_outcome = forms.ChoiceField(
        choices=MOCK_OUTCOME_CHOICES,
        initial="successful",
        label="Simulate provider outcome (MOCK/SANDBOX only)",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})
