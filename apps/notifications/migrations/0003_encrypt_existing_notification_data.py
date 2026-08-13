# Step 2 of 3 (ARCHITECTURE_DECISIONS ADR-032).

from django.db import migrations

from apps.core.encrypted_fields import _fernet, compute_lookup_hash


def encrypt_existing_rows(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    for notification in Notification.objects.all().iterator():
        recipient = notification.recipient or ""
        Notification.objects.filter(pk=notification.pk).update(
            recipient=_fernet().encrypt(recipient.encode("utf-8")).decode("utf-8") if recipient else recipient,
            recipient_lookup_hash=compute_lookup_hash(recipient),
        )


def decrypt_existing_rows(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    for notification in Notification.objects.exclude(recipient="").iterator():
        try:
            plaintext = _fernet().decrypt(notification.recipient.encode("utf-8")).decode("utf-8")
        except Exception:  # noqa: BLE001
            continue
        Notification.objects.filter(pk=notification.pk).update(recipient=plaintext)


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_add_encryption'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_rows, decrypt_existing_rows),
    ]
