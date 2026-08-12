"""Seeds the MOCK/SANDBOX provider catalog row so every fresh install has
something apps.providers.registry.get_adapter() can resolve out of the
box. This is the only provider in this codebase — see mock.py's
docstring."""

from django.db import migrations


def seed_mock_provider(apps, schema_editor):
    PaymentProvider = apps.get_model("providers", "PaymentProvider")
    PaymentChannel = apps.get_model("providers", "PaymentChannel")

    provider, _ = PaymentProvider.objects.get_or_create(
        code="mock",
        defaults={"name": "Mock / Sandbox Provider", "is_sandbox": True, "is_active": True},
    )
    PaymentChannel.objects.get_or_create(
        provider=provider,
        code="mock-mobile-money",
        defaults={"name": "Mock Mobile Money", "channel_type": "mobile_money", "is_active": True},
    )


def unseed_mock_provider(apps, schema_editor):
    PaymentProvider = apps.get_model("providers", "PaymentProvider")
    PaymentProvider.objects.filter(code="mock").delete()


class Migration(migrations.Migration):
    dependencies = [("providers", "0001_initial")]

    operations = [migrations.RunPython(seed_mock_provider, unseed_mock_provider)]
