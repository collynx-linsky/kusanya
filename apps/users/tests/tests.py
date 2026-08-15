import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError

from apps.users.models import PlatformMembership, PlatformRole

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    def test_user_model_has_no_username_database_field(self):
        with pytest.raises(FieldDoesNotExist):
            User._meta.get_field("username")

    def test_user_is_created_with_normalized_email(self):
        # BaseUserManager.normalize_email lowercases only the domain part.
        user = User.objects.create_user(email="Person@Example.com", password="Str0ngPassw0rd!")
        assert user.email == "Person@example.com"
        assert User.USERNAME_FIELD == "email"

    def test_email_must_be_unique(self):
        User.objects.create_user(email="dup@example.com", password="Str0ngPassw0rd!")
        with pytest.raises(IntegrityError):
            User.objects.create_user(email="dup@example.com", password="Str0ngPassw0rd!")

    def test_create_superuser_sets_staff_and_superuser_flags(self):
        user = User.objects.create_superuser(email="root@example.com", password="Str0ngPassw0rd!")
        assert user.is_staff is True
        assert user.is_superuser is True

    def test_password_is_hashed_not_stored_in_plaintext(self):
        user = User.objects.create_user(email="secure@example.com", password="Str0ngPassw0rd!")
        assert user.password != "Str0ngPassw0rd!"
        assert user.check_password("Str0ngPassw0rd!")


@pytest.mark.django_db
class TestPlatformMembership:
    def test_duplicate_role_grant_is_rejected(self, make_user):
        user = make_user()
        PlatformMembership.objects.create(user=user, role=PlatformRole.AUDITOR)
        with pytest.raises(IntegrityError):
            PlatformMembership.objects.create(user=user, role=PlatformRole.AUDITOR)


@pytest.mark.django_db
class TestPlatformUserCreate:
    """apps.users.views.platform_user_create -- the in-app alternative
    to Django admin for creating a user, per ARCHITECTURE_DECISIONS
    ADR-043."""

    def _platform_admin(self, make_user, make_platform_role):
        admin = make_user(email="platform-admin@example.com", is_staff=True)
        make_platform_role(admin, PlatformRole.SUPER_ADMIN)
        return admin

    def test_non_staff_cannot_reach_it(self, client, make_user):
        from django.urls import reverse

        non_staff = make_user(email="notstaff@example.com")
        client.force_login(non_staff)
        response = client.get(reverse("users:platform-create"))
        assert response.status_code == 403

    def test_creates_a_tenant_member(self, client, make_user, make_tenant, make_platform_role):
        from django.urls import reverse

        from apps.tenants.models import TenantMembership, TenantRole

        admin = self._platform_admin(make_user, make_platform_role)
        tenant = make_tenant(name="Riverside Academy")
        client.force_login(admin)

        response = client.post(
            reverse("users:platform-create"),
            {
                "first_name": "Grace",
                "last_name": "Mwangi",
                "email": "grace@riverside.example",
                "password": "SuperSecurePass123!",
                "access_type": "tenant_member",
                "tenant": tenant.id,
                "tenant_role": TenantRole.BILLING_OFFICER,
            },
        )
        assert response.status_code == 302

        new_user = User.objects.get(email="grace@riverside.example")
        assert new_user.check_password("SuperSecurePass123!")
        membership = TenantMembership.objects.get(user=new_user, tenant=tenant)
        assert membership.role == TenantRole.BILLING_OFFICER
        assert membership.invited_by == admin

    def test_creates_platform_staff_and_sets_is_staff(self, client, make_user, make_platform_role):
        from django.urls import reverse

        admin = self._platform_admin(make_user, make_platform_role)
        client.force_login(admin)

        response = client.post(
            reverse("users:platform-create"),
            {
                "first_name": "Amos",
                "last_name": "Kariuki",
                "email": "amos@kusanya.example",
                "password": "SuperSecurePass123!",
                "access_type": "platform_staff",
                "platform_role": PlatformRole.SUPPORT_ADMIN,
            },
        )
        assert response.status_code == 302

        new_user = User.objects.get(email="amos@kusanya.example")
        assert new_user.is_staff is True
        assert PlatformMembership.objects.filter(user=new_user, role=PlatformRole.SUPPORT_ADMIN).exists()

    def test_tenant_member_without_a_tenant_selected_is_rejected(
        self, client, make_user, make_platform_role
    ):
        from django.urls import reverse

        admin = self._platform_admin(make_user, make_platform_role)
        client.force_login(admin)

        response = client.post(
            reverse("users:platform-create"),
            {
                "first_name": "No",
                "last_name": "Tenant",
                "email": "notenant@example.com",
                "password": "SuperSecurePass123!",
                "access_type": "tenant_member",
            },
        )
        assert response.status_code == 200  # re-renders with a validation error
        assert not User.objects.filter(email="notenant@example.com").exists()
