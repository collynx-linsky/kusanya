# Step 1 of 2 for encrypting SettlementBatch.notes (ARCHITECTURE_DECISIONS
# ADR-032). No column-widening needed — already TextField.

from django.db import migrations

from apps.core.encrypted_fields import _fernet


def encrypt_existing_rows(apps, schema_editor):
    SettlementBatch = apps.get_model("settlement", "SettlementBatch")
    for batch in SettlementBatch.objects.exclude(notes="").iterator():
        ciphertext = _fernet().encrypt(batch.notes.encode("utf-8")).decode("utf-8")
        SettlementBatch.objects.filter(pk=batch.pk).update(notes=ciphertext)


def decrypt_existing_rows(apps, schema_editor):
    SettlementBatch = apps.get_model("settlement", "SettlementBatch")
    for batch in SettlementBatch.objects.exclude(notes="").iterator():
        try:
            plaintext = _fernet().decrypt(batch.notes.encode("utf-8")).decode("utf-8")
        except Exception:  # noqa: BLE001
            continue
        SettlementBatch.objects.filter(pk=batch.pk).update(notes=plaintext)


class Migration(migrations.Migration):

    dependencies = [
        ('settlement', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_rows, decrypt_existing_rows),
    ]
