from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.tenants.models import Sector, Tenant

User = get_user_model()


class TenantOnboardingForm(forms.Form):
    """Journey A (build spec section 47): institution registration.

    Creates the tenant (status=PENDING) and its first admin user in one
    transaction. The tenant is not usable until a platform administrator
    approves it — see apps.tenants.views.approve_tenant.
    """

    institution_name = forms.CharField(max_length=200, label="Institution / business name")
    sector = forms.ChoiceField(choices=Sector.choices)
    contact_email = forms.EmailField(label="Institution contact email")
    contact_phone = forms.CharField(max_length=32, required=False)

    admin_first_name = forms.CharField(max_length=150, label="Your first name")
    admin_last_name = forms.CharField(max_length=150, label="Your last name")
    admin_email = forms.EmailField(label="Your email (used to sign in)")
    admin_password = forms.CharField(widget=forms.PasswordInput, min_length=12, label="Password")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})

    def clean_admin_email(self):
        email = self.cleaned_data["admin_email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_institution_name(self):
        name = self.cleaned_data["institution_name"].strip()
        if Tenant.objects.filter(name__iexact=name).exists():
            raise ValidationError("An institution with this name is already registered.")
        return name
