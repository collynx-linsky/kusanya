# Step 2 of 3 (ARCHITECTURE_DECISIONS ADR-032).

from django.db import migrations

from apps.core.encrypted_fields import _fernet


def encrypt_existing_rows(apps, schema_editor):
    Branch = apps.get_model("organizations", "Branch")
    for branch in Branch.objects.exclude(address="").iterator():
        ciphertext = _fernet().encrypt(branch.address.encode("utf-8")).decode("utf-8")
        Branch.objects.filter(pk=branch.pk).update(address=ciphertext)


def decrypt_existing_rows(apps, schema_editor):
    Branch = apps.get_model("organizations", "Branch")
    for branch in Branch.objects.exclude(address="").iterator():
        try:
            plaintext = _fernet().decrypt(branch.address.encode("utf-8")).decode("utf-8")
        except Exception:  # noqa: BLE001
            continue
        Branch.objects.filter(pk=branch.pk).update(address=plaintext)


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0003_widen_branch_address'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_rows, decrypt_existing_rows),
    ]
