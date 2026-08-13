# Step 3 of 3 (ARCHITECTURE_DECISIONS ADR-032).

import apps.core.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_encrypt_existing_user_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='first_name',
            field=apps.core.encrypted_fields.EncryptedCharField(blank=True, max_length=150),
        ),
        migrations.AlterField(
            model_name='user',
            name='last_name',
            field=apps.core.encrypted_fields.EncryptedCharField(blank=True, max_length=150),
        ),
        migrations.AlterField(
            model_name='user',
            name='phone_number',
            field=apps.core.encrypted_fields.EncryptedCharField(blank=True, max_length=32),
        ),
    ]
