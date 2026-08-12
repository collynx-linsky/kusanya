from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.settlement.forms import GenerateSettlementBatchForm, MarkSettlementCompletedForm
from apps.settlement.models import SettlementBatch
from apps.settlement.services import generate_settlement_batch, mark_settlement_completed
from apps.tenants.permissions import require_platform_role
from apps.users.models import PlatformRole


@login_required
def batch_list(request):
    """Read-only for tenant users — settlement generation/completion is a
    platform-controlled action (see models.py's regulatory framing)."""
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    batches = SettlementBatch.objects.filter(tenant=request.tenant)
    return render(request, "settlement/list.html", {"batches": batches})


@login_required
def batch_detail(request, pk):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    batch = get_object_or_404(SettlementBatch, pk=pk, tenant=request.tenant)
    return render(request, "settlement/detail.html", {"batch": batch})


@login_required
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.FINANCE_ADMIN)
def generate_batch(request):
    if request.method == "POST":
        form = GenerateSettlementBatchForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            batch = generate_settlement_batch(
                tenant=data["tenant"],
                provider=data["provider"],
                period_start=data["period_start"],
                period_end=data["period_end"],
                actor=request.user,
            )
            messages.success(
                request,
                f"Settlement batch {batch.reference} generated: "
                f"{batch.payments.count()} payment(s), net {batch.net_amount} {batch.currency}.",
            )
            return redirect("settlement:platform-list")
    else:
        form = GenerateSettlementBatchForm()
    return render(request, "settlement/generate_form.html", {"form": form})


@login_required
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.FINANCE_ADMIN)
def platform_batch_list(request):
    batches = SettlementBatch.objects.select_related("tenant", "provider").all()[:200]
    return render(request, "settlement/platform_list.html", {"batches": batches})


@login_required
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.FINANCE_ADMIN)
def mark_completed(request, pk):
    batch = get_object_or_404(SettlementBatch, pk=pk)
    if request.method == "POST":
        form = MarkSettlementCompletedForm(request.POST)
        if form.is_valid():
            mark_settlement_completed(
                batch,
                external_settlement_reference=form.cleaned_data["external_settlement_reference"],
                actor=request.user,
            )
            messages.success(request, f"Settlement batch {batch.reference} marked completed.")
            return redirect("settlement:platform-list")
    else:
        form = MarkSettlementCompletedForm()
    return render(request, "settlement/mark_completed_form.html", {"form": form, "batch": batch})
