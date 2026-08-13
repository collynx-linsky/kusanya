# Step 2 of 3 (ARCHITECTURE_DECISIONS ADR-032).

from django.db import migrations

from apps.core.encrypted_fields import _fernet, compute_lookup_hash


def encrypt_existing_rows(apps, schema_editor):
    User = apps.get_model("users", "User")
    for user in User.objects.all().iterator():
        first_name = user.first_name or ""
        last_name = user.last_name or ""
        phone_number = user.phone_number or ""
        User.objects.filter(pk=user.pk).update(
            first_name=_fernet().encrypt(first_name.encode("utf-8")).decode("utf-8") if first_name else first_name,
            last_name=_fernet().encrypt(last_name.encode("utf-8")).decode("utf-8") if last_name else last_name,
            phone_number=(
                _fernet().encrypt(phone_number.encode("utf-8")).decode("utf-8") if phone_number else phone_number
            ),
            first_name_lookup_hash=compute_lookup_hash(first_name) if first_name else "",
            last_name_lookup_hash=compute_lookup_hash(last_name) if last_name else "",
        )


def decrypt_existing_rows(apps, schema_editor):
    User = apps.get_model("users", "User")
    for user in User.objects.all().iterator():
        updates = {}
        for field in ("first_name", "last_name", "phone_number"):
            value = getattr(user, field) or ""
            if value:
                try:
                    updates[field] = _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
                except Exception:  # noqa: BLE001
                    pass
        if updates:
            User.objects.filter(pk=user.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_add_encryption'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_rows, decrypt_existing_rows),
    ]
