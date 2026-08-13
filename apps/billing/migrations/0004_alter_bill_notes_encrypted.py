# Step 2 of 2 (ARCHITECTURE_DECISIONS ADR-032) — safe now that 0003 has
# re-encoded every existing row as ciphertext.

import apps.core.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_encrypt_existing_bill_notes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bill',
            name='notes',
            field=apps.core.encrypted_fields.EncryptedTextField(blank=True),
        ),
    ]
