# Step 2 of 2 (ARCHITECTURE_DECISIONS ADR-032).

import apps.core.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('settlement', '0002_encrypt_existing_notes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='settlementbatch',
            name='notes',
            field=apps.core.encrypted_fields.EncryptedTextField(blank=True),
        ),
    ]
