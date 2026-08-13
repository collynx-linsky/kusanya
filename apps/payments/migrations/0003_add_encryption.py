# Step 1 of 3 for encrypting Payment.payer_reference
# (ARCHITECTURE_DECISIONS ADR-032): add the lookup_hash column and
# widen to TEXT *before* encrypting (0004) — ciphertext is longer than
# the original varchar(100) limit.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_payment_settlement_batch'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='payer_reference_lookup_hash',
            field=models.CharField(blank=True, db_index=True, default='', editable=False, max_length=64),
        ),
        migrations.AlterField(
            model_name='payment',
            name='payer_reference',
            field=models.TextField(blank=True),
        ),
    ]
