# Step 1 of 3 for encrypting User.first_name/last_name/phone_number
# (ARCHITECTURE_DECISIONS ADR-032): add the lookup_hash columns and
# widen the three target columns to TEXT *before* encrypting (0003) —
# ciphertext is longer than the original varchar limits. User.email is
# deliberately NOT touched here — see User's docstring for why.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='first_name_lookup_hash',
            field=models.CharField(blank=True, db_index=True, default='', editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name='user',
            name='last_name_lookup_hash',
            field=models.CharField(blank=True, db_index=True, default='', editable=False, max_length=64),
        ),
        migrations.AlterField(
            model_name='user',
            name='first_name',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='last_name',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='phone_number',
            field=models.TextField(blank=True),
        ),
    ]
