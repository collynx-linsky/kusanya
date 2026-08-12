import pytest
from django.contrib.auth import get_user_model

from apps.tenants.models import Tenant, TenantMembership, TenantRole
from apps.users.models import PlatformMembership, PlatformRole

User = get_user_model()


@pytest.fixture
def make_user(db):
    def _make(email="user@example.com", password="Str0ngPassw0rd!", **kwargs):
        return User.objects.create_user(email=email, password=password, **kwargs)

    return _make


@pytest.fixture
def make_tenant(db):
    def _make(name="Test Institution", status=Tenant.Status.ACTIVE, **kwargs):
        return Tenant.objects.create(
            name=name, contact_email="contact@example.com", status=status, **kwargs
        )

    return _make


@pytest.fixture
def make_membership(db):
    def _make(user, tenant, role=TenantRole.ADMIN, is_active=True):
        return TenantMembership.objects.create(
            user=user, tenant=tenant, role=role, is_active=is_active
        )

    return _make


@pytest.fixture
def make_platform_role(db):
    def _make(user, role=PlatformRole.SUPER_ADMIN):
        return PlatformMembership.objects.create(user=user, role=role)

    return _make


@pytest.fixture
def make_customer(db):
    from apps.customers.models import Customer

    def _make(tenant, full_name="Jane Payer", **kwargs):
        return Customer.objects.create(tenant=tenant, full_name=full_name, **kwargs)

    return _make


@pytest.fixture
def make_customer_account(db):
    from apps.customers.models import CustomerAccount

    def _make(tenant, customer, name="Test Account", **kwargs):
        return CustomerAccount.objects.create(tenant=tenant, customer=customer, name=name, **kwargs)

    return _make
