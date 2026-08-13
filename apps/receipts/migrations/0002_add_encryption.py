# Step 1 of 3 for encrypting Receipt.customer_name (ARCHITECTURE_DECISIONS
# ADR-032): add the lookup_hash column and widen to TEXT *before*
# encrypting (0003) — ciphertext is longer than the original
# varchar(255) limit.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('receipts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='receipt',
            name='customer_name_lookup_hash',
            field=models.CharField(db_index=True, default='', editable=False, max_length=64),
        ),
        migrations.AlterField(
            model_name='receipt',
            name='customer_name',
            field=models.TextField(),
        ),
    ]
