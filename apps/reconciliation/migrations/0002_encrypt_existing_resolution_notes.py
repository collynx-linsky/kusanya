# Step 1 of 2 for encrypting ReconciliationException.resolution_notes
# (ARCHITECTURE_DECISIONS ADR-032). No column-widening needed — already
# TextField.

from django.db import migrations

from apps.core.encrypted_fields import _fernet


def encrypt_existing_rows(apps, schema_editor):
    ReconciliationException = apps.get_model("reconciliation", "ReconciliationException")
    for exc in ReconciliationException.objects.exclude(resolution_notes="").iterator():
        ciphertext = _fernet().encrypt(exc.resolution_notes.encode("utf-8")).decode("utf-8")
        ReconciliationException.objects.filter(pk=exc.pk).update(resolution_notes=ciphertext)


def decrypt_existing_rows(apps, schema_editor):
    ReconciliationException = apps.get_model("reconciliation", "ReconciliationException")
    for exc in ReconciliationException.objects.exclude(resolution_notes="").iterator():
        try:
            plaintext = _fernet().decrypt(exc.resolution_notes.encode("utf-8")).decode("utf-8")
        except Exception:  # noqa: BLE001
            continue
        ReconciliationException.objects.filter(pk=exc.pk).update(resolution_notes=plaintext)


class Migration(migrations.Migration):

    dependencies = [
        ('reconciliation', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_rows, decrypt_existing_rows),
    ]
