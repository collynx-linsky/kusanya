# Step 1 of 3 for encrypting Customer.full_name/email/phone_number
# (ARCHITECTURE_DECISIONS ADR-032): add the lookup_hash columns, the new
# (non-PII) Meta.ordering, and widen the three target columns to
# unbounded TEXT — *before* any data is encrypted (0003), because
# ciphertext is longer than the original varchar(32)/varchar(254) limits
# and would truncate/error otherwise. The field is still a plain
# TextField here, not EncryptedCharField yet — that swap is 0004, after
# 0003 has re-encoded the actual row data.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='customer',
            options={'ordering': ['-created_at']},
        ),
        migrations.AlterModelOptions(
            name='customeraccount',
            options={'ordering': ['customer_id', 'name']},
        ),
        migrations.AddField(
            model_name='customer',
            name='email_lookup_hash',
            field=models.CharField(blank=True, db_index=True, default='', editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name='customer',
            name='full_name_lookup_hash',
            field=models.CharField(db_index=True, default='', editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name='customer',
            name='phone_number_lookup_hash',
            field=models.CharField(blank=True, db_index=True, default='', editable=False, max_length=64),
        ),
        migrations.AlterField(
            model_name='customer',
            name='email',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='customer',
            name='full_name',
            field=models.TextField(),
        ),
        migrations.AlterField(
            model_name='customer',
            name='phone_number',
            field=models.TextField(blank=True),
        ),
    ]
