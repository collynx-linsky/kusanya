# Step 3 of 3 (ARCHITECTURE_DECISIONS ADR-032).

import apps.core.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0004_encrypt_existing_payment_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='payer_reference',
            field=apps.core.encrypted_fields.EncryptedCharField(blank=True, max_length=100),
        ),
    ]
