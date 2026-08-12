from django import forms

from apps.billing.models import RevenueSource
from apps.customers.models import CustomerAccount


class QuickBillForm(forms.Form):
    """Single-line-item bill creation for the portal.

    Multi-item bills are fully supported by the data model and by
    `apps.billing.services.get_or_create_bill` (which takes an arbitrary
    items list) — this form is a deliberately simple portal shortcut, not
    a limitation of the underlying engine. Multi-item bill entry through
    the portal is not yet built; use the admin or (once it exists) the
    API for that.
    """

    customer_account = forms.ModelChoiceField(queryset=CustomerAccount.objects.none())
    revenue_source = forms.ModelChoiceField(
        queryset=RevenueSource.objects.none(), required=False
    )
    description = forms.CharField(max_length=255)
    unit_amount = forms.DecimalField(max_digits=18, decimal_places=2, min_value=0.01)
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    external_reference = forms.CharField(max_length=100, required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["customer_account"].queryset = CustomerAccount.objects.filter(
                tenant=tenant, is_active=True
            )
            self.fields["revenue_source"].queryset = RevenueSource.objects.filter(
                tenant=tenant, is_active=True
            )
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})
