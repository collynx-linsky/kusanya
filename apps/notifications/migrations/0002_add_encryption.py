# Step 1 of 3 for encrypting Notification.recipient (ARCHITECTURE_DECISIONS
# ADR-032): add the lookup_hash column and widen to TEXT *before*
# encrypting (0003) — ciphertext is longer than the original
# varchar(255) limit. Still a plain TextField here, not
# EncryptedCharField yet (that's 0004).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='recipient_lookup_hash',
            field=models.CharField(db_index=True, default='', editable=False, max_length=64),
        ),
        migrations.AlterField(
            model_name='notification',
            name='recipient',
            field=models.TextField(help_text='Email address or phone number.'),
        ),
    ]
