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
