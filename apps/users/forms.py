from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.core.forms import KusanyaFormHelperMixin
from apps.tenants.models import Tenant, TenantRole
from apps.users.models import PlatformRole

User = get_user_model()

ACCESS_TENANT_MEMBER = "tenant_member"
ACCESS_PLATFORM_STAFF = "platform_staff"

# API_CLIENT is a service-account role paired with the API credentials
# flow, not something handed to a person here -- same reasoning as
# apps.tenants.forms.TeamMemberForm.
_TENANT_ROLE_CHOICES = [c for c in TenantRole.choices if c[0] != TenantRole.API_CLIENT]


class PlatformUserCreateForm(KusanyaFormHelperMixin, forms.Form):
    """Platform staff creating a user directly -- the in-app
    alternative to Django admin for this, same reasoning as
    apps.tenants.views.platform_create_tenant (ARCHITECTURE_DECISIONS
    ADR-041/043). Grants EITHER membership in one existing institution
    OR platform-staff access, never both in one submission -- kept as
    two distinct grants, mirroring TenantMembership/PlatformMembership
    being two separate models, rather than one form pretending they're
    interchangeable."""

    ACCESS_CHOICES = [
        (ACCESS_TENANT_MEMBER, "Member of an institution"),
        (ACCESS_PLATFORM_STAFF, "KUSANYA platform staff"),
    ]

    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")
    email = forms.EmailField(label="Email (used to sign in)")
    password = forms.CharField(widget=forms.PasswordInput, min_length=12, label="Password")
    access_type = forms.ChoiceField(
        choices=ACCESS_CHOICES, widget=forms.RadioSelect, label="Access", initial=ACCESS_TENANT_MEMBER
    )
    tenant = forms.ModelChoiceField(
        queryset=Tenant.objects.filter(status=Tenant.Status.ACTIVE).order_by("name"),
        required=False,
        label="Institution",
    )
    tenant_role = forms.ChoiceField(choices=_TENANT_ROLE_CHOICES, required=False, label="Role at that institution")
    platform_role = forms.ChoiceField(choices=PlatformRole.choices, required=False, label="Platform role")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        access = cleaned.get("access_type")
        if access == ACCESS_TENANT_MEMBER:
            if not cleaned.get("tenant"):
                self.add_error("tenant", "Choose which institution this person belongs to.")
            if not cleaned.get("tenant_role"):
                self.add_error("tenant_role", "Choose their role at that institution.")
        elif access == ACCESS_PLATFORM_STAFF:
            if not cleaned.get("platform_role"):
                self.add_error("platform_role", "Choose their platform role.")
        return cleaned
