from django import forms

from apps.customers.models import Customer, CustomerAccount


class _BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})


class CustomerForm(_BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["full_name", "email", "phone_number", "external_reference"]


class CustomerAccountForm(_BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CustomerAccount
        fields = ["name", "revenue_source", "external_reference"]

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["revenue_source"].queryset = self.fields["revenue_source"].queryset.filter(
                tenant=tenant
            )
