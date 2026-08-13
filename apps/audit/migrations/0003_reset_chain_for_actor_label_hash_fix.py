# Data migration for ARCHITECTURE_DECISIONS ADR-035.
#
# apps.audit.models.AuditLog._canonical_payload() previously hashed
# `actor_id` (the live, mutable FK column) rather than `actor_label`
# (the immutable snapshot the model already maintains specifically to
# survive actor deletion). Since `AuditLog.actor` is on_delete=SET_NULL,
# deleting any user who ever performed an audited action silently
# changed `actor_id` on their historical records after the fact --
# meaning `AuditLog.verify_chain()` would report those records as
# "tampered with" even though nothing malicious happened. Found live,
# not theoretically: building the chain-verification UI
# (apps.audit.views.verify_chain) surfaced a real failure the first
# time it ran against genuine development data.
#
# AuditLog blocks .save() on existing rows (by design -- immutability),
# so a stored record_hash computed under the old (buggy) formula can
# never be corrected in place. Every row's hash also depends on every
# prior row's hash (it's a chain), so this isn't a per-row fix -- the
# whole chain has to restart from GENESIS_HASH under the corrected
# formula. This project has no production deployment yet; every row
# that already existed here was development/smoke-test data generated
# during this build, not real audit history -- so clearing the table
# and letting it rebuild from an empty, correct chain is the honest
# resolution. This would NOT be the correct move against real
# production audit data (see ADR-035's own text for what that
# situation would actually require).

from django.db import migrations


def reset_chain(apps, schema_editor):
    AuditLog = apps.get_model("audit", "AuditLog")
    # Bulk queryset .delete() bypasses the model's own delete() override
    # (which raises AuditLogImmutableError on instance-level deletes) --
    # deliberate here, see the module docstring above.
    AuditLog.objects.all().delete()


def noop_reverse(apps, schema_editor):
    # Nothing meaningful to reverse -- the deleted rows are gone either
    # way, and re-migrating backwards to "before the fix" shouldn't
    # resurrect data that was already accepted as unrecoverable.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(reset_chain, noop_reverse),
    ]
