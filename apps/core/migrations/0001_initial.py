from django.db import migrations


class Migration(migrations.Migration):
    """apps.core has no concrete models of its own (BaseModel/TenantScopedModel
    are abstract) — this migration exists only as an anchor for
    0002_seed_health_monitor_schedule to depend on."""

    initial = True

    dependencies = []

    operations = []
