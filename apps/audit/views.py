"""Platform-staff-only audit views. The hash chain (AuditLog.verify_chain,
model.py) links records in a single global sequence — not one chain per
tenant — so integrity verification only makes sense platform-wide, not
scoped to any one tenant's records. See docs/DESIGN_SYSTEM.md's "Audit
visualization" section and ARCHITECTURE_DECISIONS ADR-006."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from apps.audit.models import AuditLog
from apps.tenants.permissions import require_platform_role
from apps.users.models import PlatformRole


@login_required
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.COMPLIANCE_ADMIN, PlatformRole.AUDITOR)
def verify_chain(request):
    if request.method == "POST":
        is_intact, broken_record = AuditLog.verify_chain()
        if is_intact:
            messages.success(request, "Audit chain integrity verified — no tampering detected.")
        else:
            messages.error(
                request,
                f"Audit chain integrity check FAILED at record {broken_record.id} "
                f"({broken_record.created_at:%Y-%m-%d %H:%M:%S} — {broken_record.action}). "
                "This requires immediate investigation.",
            )
    return redirect("core:platform-dashboard")
