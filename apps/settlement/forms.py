from django import forms

from apps.providers.models import PaymentProvider
from apps.tenants.models import Tenant


class GenerateSettlementBatchForm(forms.Form):
    tenant = forms.ModelChoiceField(queryset=Tenant.objects.filter(status=Tenant.Status.ACTIVE))
    provider = forms.ModelChoiceField(queryset=PaymentProvider.objects.filter(is_active=True))
    period_start = forms.DateTimeField(widget=forms.DateInput(attrs={"type": "date"}))
    period_end = forms.DateTimeField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})


class MarkSettlementCompletedForm(forms.Form):
    external_settlement_reference = forms.CharField(
        max_length=150, label="Provider/bank settlement reference"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})
