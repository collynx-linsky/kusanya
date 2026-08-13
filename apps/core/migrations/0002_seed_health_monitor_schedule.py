"""Seeds the Celery Beat schedule entry for apps.core.tasks.monitor_system_health
(see ARCHITECTURE_DECISIONS ADR-031). Data, not schema — reversible by
deleting the row it creates, not by dropping a table."""

from django.db import migrations

TASK_NAME = "Monitor system health"
TASK_PATH = "apps.core.tasks.monitor_system_health"


def seed_schedule(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = IntervalSchedule.objects.get_or_create(every=5, period="minutes")
    PeriodicTask.objects.get_or_create(
        name=TASK_NAME,
        defaults={"task": TASK_PATH, "interval": schedule, "enabled": True},
    )


def remove_schedule(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME, task=TASK_PATH).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(seed_schedule, remove_schedule),
    ]
