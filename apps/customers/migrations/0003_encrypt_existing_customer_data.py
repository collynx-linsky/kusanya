# Step 2 of 3 (ARCHITECTURE_DECISIONS ADR-032): re-encode every existing
# Customer row's full_name/email/phone_number from plaintext to Fernet
# ciphertext, and populate the lookup_hash columns 0002 added — all
# while the field is STILL the plain CharField/EmailField Django
# recorded in migration history (`apps.get_model` gives the historical
# model, whose fields don't know about EncryptedCharField at all, so
# `.update()` here writes the computed ciphertext string as a literal
# value, not double-encrypted). Only after this has run is it safe for
# 0004 to swap the field class to EncryptedCharField — reading through
# that field before this step would try to Fernet-decrypt plaintext and
# get "[unreadable: decryption failed]" for every existing customer.

from django.db import migrations

from apps.core.encrypted_fields import compute_lookup_hash


def _fernet_encrypt(value: str) -> str:
    from apps.core.encrypted_fields import _fernet

    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def encrypt_existing_rows(apps, schema_editor):
    Customer = apps.get_model("customers", "Customer")
    for customer in Customer.objects.all().iterator():
        full_name = customer.full_name or ""
        email = customer.email or ""
        phone_number = customer.phone_number or ""
        Customer.objects.filter(pk=customer.pk).update(
            full_name=_fernet_encrypt(full_name) if full_name else full_name,
            email=_fernet_encrypt(email) if email else email,
            phone_number=_fernet_encrypt(phone_number) if phone_number else phone_number,
            full_name_lookup_hash=compute_lookup_hash(full_name),
            email_lookup_hash=compute_lookup_hash(email.lower()) if email else "",
            phone_number_lookup_hash=compute_lookup_hash(phone_number),
        )


def decrypt_existing_rows(apps, schema_editor):
    """Reverse: only meaningful if run before 0004 has applied (field is
    still plain at this point in the graph) — decrypts back to
    plaintext, for symmetry/reversibility, not because anyone expects to
    actually run this against production data."""
    from apps.core.encrypted_fields import _fernet

    Customer = apps.get_model("customers", "Customer")
    for customer in Customer.objects.all().iterator():
        updates = {}
        for field in ("full_name", "email", "phone_number"):
            value = getattr(customer, field) or ""
            if value:
                try:
                    updates[field] = _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
                except Exception:  # noqa: BLE001 — best-effort reversal
                    pass
        if updates:
            Customer.objects.filter(pk=customer.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0002_add_encryption'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_rows, decrypt_existing_rows),
    ]
