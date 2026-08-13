# Step 3 of 3 (ARCHITECTURE_DECISIONS ADR-032).

import apps.core.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_encrypt_existing_notification_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='recipient',
            field=apps.core.encrypted_fields.EncryptedCharField(
                help_text='Email address or phone number.', max_length=255
            ),
        ),
    ]
