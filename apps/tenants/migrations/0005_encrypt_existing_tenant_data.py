# Step 2 of 3 (ARCHITECTURE_DECISIONS ADR-032).

from django.db import migrations

from apps.core.encrypted_fields import _fernet, compute_lookup_hash


def encrypt_existing_rows(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for tenant in Tenant.objects.all().iterator():
        contact_email = tenant.contact_email or ""
        contact_phone = tenant.contact_phone or ""
        Tenant.objects.filter(pk=tenant.pk).update(
            contact_email=(
                _fernet().encrypt(contact_email.encode("utf-8")).decode("utf-8")
                if contact_email
                else contact_email
            ),
            contact_phone=(
                _fernet().encrypt(contact_phone.encode("utf-8")).decode("utf-8")
                if contact_phone
                else contact_phone
            ),
            contact_email_lookup_hash=compute_lookup_hash(contact_email.lower()) if contact_email else "",
        )


def decrypt_existing_rows(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for tenant in Tenant.objects.all().iterator():
        updates = {}
        for field in ("contact_email", "contact_phone"):
            value = getattr(tenant, field) or ""
            if value:
                try:
                    updates[field] = _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
                except Exception:  # noqa: BLE001
                    pass
        if updates:
            Tenant.objects.filter(pk=tenant.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0004_add_encryption'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_rows, decrypt_existing_rows),
    ]
