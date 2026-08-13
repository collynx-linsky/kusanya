# Step 2 of 3 (ARCHITECTURE_DECISIONS ADR-032).

from django.db import migrations

from apps.core.encrypted_fields import _fernet, compute_lookup_hash


def encrypt_existing_rows(apps, schema_editor):
    Payment = apps.get_model("payments", "Payment")
    for payment in Payment.objects.all().iterator():
        payer_reference = payment.payer_reference or ""
        Payment.objects.filter(pk=payment.pk).update(
            payer_reference=(
                _fernet().encrypt(payer_reference.encode("utf-8")).decode("utf-8")
                if payer_reference
                else payer_reference
            ),
            payer_reference_lookup_hash=compute_lookup_hash(payer_reference),
        )


def decrypt_existing_rows(apps, schema_editor):
    Payment = apps.get_model("payments", "Payment")
    for payment in Payment.objects.exclude(payer_reference="").iterator():
        try:
            plaintext = _fernet().decrypt(payment.payer_reference.encode("utf-8")).decode("utf-8")
        except Exception:  # noqa: BLE001
            continue
        Payment.objects.filter(pk=payment.pk).update(payer_reference=plaintext)


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0003_add_encryption'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_rows, decrypt_existing_rows),
    ]
