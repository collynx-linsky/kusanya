# Step 1 of 2 for encrypting Bill.notes (ARCHITECTURE_DECISIONS ADR-032).
# No column-widening needed here — notes was already TextField, and
# ciphertext fits fine in TEXT. Re-encodes existing rows from plaintext
# to Fernet ciphertext while the field is still the plain TextField
# Django recorded in migration history; 0004 then swaps the field class.

from django.db import migrations

from apps.core.encrypted_fields import _fernet


def encrypt_existing_rows(apps, schema_editor):
    Bill = apps.get_model("billing", "Bill")
    for bill in Bill.objects.exclude(notes="").iterator():
        ciphertext = _fernet().encrypt(bill.notes.encode("utf-8")).decode("utf-8")
        Bill.objects.filter(pk=bill.pk).update(notes=ciphertext)


def decrypt_existing_rows(apps, schema_editor):
    Bill = apps.get_model("billing", "Bill")
    for bill in Bill.objects.exclude(notes="").iterator():
        try:
            plaintext = _fernet().decrypt(bill.notes.encode("utf-8")).decode("utf-8")
        except Exception:  # noqa: BLE001 — best-effort reversal
            continue
        Bill.objects.filter(pk=bill.pk).update(notes=plaintext)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_rows, decrypt_existing_rows),
    ]
