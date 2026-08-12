from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.reconciliation.models import ExceptionStatus, ReconciliationException, ReconciliationRun
from apps.reconciliation.services import resolve_exception, run_reconciliation
from apps.tenants.models import TenantRole
from apps.tenants.permissions import require_tenant_role

_CAN_MANAGE = (TenantRole.ADMIN, TenantRole.FINANCE_MANAGER, TenantRole.RECONCILIATION_OFFICER)


@login_required
def run_list(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    runs = ReconciliationRun.objects.filter(tenant=request.tenant)
    open_exceptions = ReconciliationException.objects.filter(tenant=request.tenant, status=ExceptionStatus.OPEN)
    return render(
        request, "reconciliation/list.html", {"runs": runs, "open_exceptions": open_exceptions}
    )


@login_required
def run_detail(request, pk):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    run = get_object_or_404(ReconciliationRun, pk=pk, tenant=request.tenant)
    exceptions = run.exceptions.select_related("payment")
    return render(request, "reconciliation/detail.html", {"run": run, "exceptions": exceptions})


@login_required
@require_tenant_role(*_CAN_MANAGE)
def trigger_run(request):
    if request.method == "POST":
        run = run_reconciliation(tenant=request.tenant, actor=request.user)
        messages.success(
            request,
            f"Reconciliation complete: {run.total_checked} checked, {run.matched_count} matched, "
            f"{run.exception_count} exception(s), {run.resolved_unknown_count} UNKNOWN payment(s) resolved.",
        )
        return redirect("reconciliation:detail", pk=run.pk)
    return redirect("reconciliation:list")


@login_required
@require_tenant_role(*_CAN_MANAGE)
def resolve_exception_view(request, pk):
    exception = get_object_or_404(ReconciliationException, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        resolve_exception(exception, actor=request.user, notes=request.POST.get("notes", ""))
        messages.success(request, "Exception marked resolved.")
    if exception.run_id:
        return redirect("reconciliation:detail", pk=exception.run_id)
    return redirect("reconciliation:list")
