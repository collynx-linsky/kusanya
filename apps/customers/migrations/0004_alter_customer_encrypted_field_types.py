# Step 3 of 3 (ARCHITECTURE_DECISIONS ADR-032): now that 0003 has
# re-encoded every existing row as ciphertext, it's safe to swap
# full_name/email/phone_number to EncryptedCharField — from this point
# on, the ORM transparently decrypts on read and encrypts on write.

import apps.core.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0003_encrypt_existing_customer_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customer',
            name='email',
            field=apps.core.encrypted_fields.EncryptedCharField(blank=True, max_length=254),
        ),
        migrations.AlterField(
            model_name='customer',
            name='full_name',
            field=apps.core.encrypted_fields.EncryptedCharField(max_length=255),
        ),
        migrations.AlterField(
            model_name='customer',
            name='phone_number',
            field=apps.core.encrypted_fields.EncryptedCharField(blank=True, max_length=32),
        ),
    ]
