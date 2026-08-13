# Step 3 of 3 (ARCHITECTURE_DECISIONS ADR-032).

import apps.core.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0004_encrypt_existing_branch_address'),
    ]

    operations = [
        migrations.AlterField(
            model_name='branch',
            name='address',
            field=apps.core.encrypted_fields.EncryptedCharField(blank=True, max_length=255),
        ),
    ]
