# Step 3 of 3 (ARCHITECTURE_DECISIONS ADR-032).

import apps.core.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('receipts', '0003_encrypt_existing_receipt_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='receipt',
            name='customer_name',
            field=apps.core.encrypted_fields.EncryptedCharField(max_length=255),
        ),
    ]
