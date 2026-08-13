# Step 1 of 3 for encrypting Tenant.contact_email/contact_phone
# (ARCHITECTURE_DECISIONS ADR-032): add the lookup_hash column and widen
# both to TEXT *before* encrypting (0005) — ciphertext is longer than
# the original varchar limits.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0003_tenant_fee_refund_policy'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='contact_email_lookup_hash',
            field=models.CharField(db_index=True, default='', editable=False, max_length=64),
        ),
        migrations.AlterField(
            model_name='tenant',
            name='contact_email',
            field=models.TextField(),
        ),
        migrations.AlterField(
            model_name='tenant',
            name='contact_phone',
            field=models.TextField(blank=True),
        ),
    ]
