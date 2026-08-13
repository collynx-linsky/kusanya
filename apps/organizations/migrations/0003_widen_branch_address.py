# Step 1 of 3 for encrypting Branch.address (ARCHITECTURE_DECISIONS
# ADR-032). Widen to TEXT *before* encrypting (0004) — ciphertext is
# longer than the original varchar(255) limit. Still a plain TextField
# here, not EncryptedCharField yet (that's 0005).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0002_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='branch',
            name='address',
            field=models.TextField(blank=True),
        ),
    ]
