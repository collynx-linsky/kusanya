import pytest
from django.db import IntegrityError

from apps.organizations.models import Branch


@pytest.mark.django_db
class TestBranch:
    def test_branch_names_must_be_unique_within_a_tenant(self, make_tenant):
        tenant = make_tenant()
        Branch.objects.create(tenant=tenant, name="Main Campus")
        with pytest.raises(IntegrityError):
            Branch.objects.create(tenant=tenant, name="Main Campus")

    def test_same_branch_name_allowed_across_different_tenants(self, make_tenant):
        tenant_a = make_tenant(name="A")
        tenant_b = make_tenant(name="B")
        Branch.objects.create(tenant=tenant_a, name="Main Campus")
        # Should not raise — uniqueness is per-tenant, not global.
        Branch.objects.create(tenant=tenant_b, name="Main Campus")
