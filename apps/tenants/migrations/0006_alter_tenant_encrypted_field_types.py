# Step 3 of 3 (ARCHITECTURE_DECISIONS ADR-032).

import apps.core.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0005_encrypt_existing_tenant_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tenant',
            name='contact_email',
            field=apps.core.encrypted_fields.EncryptedCharField(max_length=254),
        ),
        migrations.AlterField(
            model_name='tenant',
            name='contact_phone',
            field=apps.core.encrypted_fields.EncryptedCharField(blank=True, max_length=32),
        ),
    ]
