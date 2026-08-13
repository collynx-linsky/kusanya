# Step 2 of 3 (ARCHITECTURE_DECISIONS ADR-032).

from django.db import migrations

from apps.core.encrypted_fields import _fernet, compute_lookup_hash


def encrypt_existing_rows(apps, schema_editor):
    Receipt = apps.get_model("receipts", "Receipt")
    for receipt in Receipt.objects.all().iterator():
        customer_name = receipt.customer_name or ""
        Receipt.objects.filter(pk=receipt.pk).update(
            customer_name=(
                _fernet().encrypt(customer_name.encode("utf-8")).decode("utf-8")
                if customer_name
                else customer_name
            ),
            customer_name_lookup_hash=compute_lookup_hash(customer_name),
        )


def decrypt_existing_rows(apps, schema_editor):
    Receipt = apps.get_model("receipts", "Receipt")
    for receipt in Receipt.objects.exclude(customer_name="").iterator():
        try:
            plaintext = _fernet().decrypt(receipt.customer_name.encode("utf-8")).decode("utf-8")
        except Exception:  # noqa: BLE001
            continue
        Receipt.objects.filter(pk=receipt.pk).update(customer_name=plaintext)


class Migration(migrations.Migration):

    dependencies = [
        ('receipts', '0002_add_encryption'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_rows, decrypt_existing_rows),
    ]
