from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.billing.forms import QuickBillForm
from apps.billing.models import Bill, BillStatus
from apps.billing.services import get_or_create_bill
from apps.control_numbers.services import get_or_create_for_bill
from apps.tenants.models import TenantRole
from apps.tenants.permissions import require_tenant_role

_CAN_MANAGE = (TenantRole.ADMIN, TenantRole.FINANCE_MANAGER, TenantRole.BILLING_OFFICER, TenantRole.ACCOUNTANT)


@login_required
def bill_list(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    bills = Bill.objects.filter(tenant=request.tenant).select_related(
        "customer_account", "customer_account__customer", "control_number"
    )
    return render(request, "billing/list.html", {"bills": bills})


@login_required
def bill_detail(request, pk):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    bill = get_object_or_404(
        Bill.objects.select_related("customer_account__customer").prefetch_related("items"),
        pk=pk,
        tenant=request.tenant,
    )
    control_number = getattr(bill, "control_number", None)
    return render(
        request, "billing/detail.html", {"bill": bill, "control_number": control_number}
    )


@login_required
@require_tenant_role(*_CAN_MANAGE)
def bill_create(request):
    if request.method == "POST":
        form = QuickBillForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            data = form.cleaned_data
            bill, created = get_or_create_bill(
                tenant=request.tenant,
                customer_account=data["customer_account"],
                revenue_source=data["revenue_source"],
                items=[{"description": data["description"], "unit_amount": data["unit_amount"]}],
                due_date=data["due_date"],
                external_reference=data["external_reference"],
                actor=request.user,
            )
            if created:
                bill.transition_to(BillStatus.ACTIVE)
                # Journey B (build spec section 47): bill -> control
                # number, in one flow — a fee will be charged for this in
                # Phase 4 only if the control number is genuinely new,
                # which get_or_create_for_bill guarantees here since this
                # bill has never had one before.
                get_or_create_for_bill(tenant=request.tenant, bill=bill, actor=request.user)
                messages.success(request, f"Bill {bill.bill_number} created and issued.")
            else:
                messages.info(request, "A bill with this reference already exists.")
            return redirect("billing:detail", pk=bill.pk)
    else:
        form = QuickBillForm(tenant=request.tenant)
    return render(request, "billing/form.html", {"form": form})


@login_required
@require_tenant_role(*_CAN_MANAGE)
def bill_cancel(request, pk):
    bill = get_object_or_404(Bill, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        try:
            bill.transition_to(BillStatus.CANCELLED)
            messages.success(request, f"Bill {bill.bill_number} cancelled.")
        except ValidationError as exc:
            messages.error(request, str(exc))
    return redirect("billing:detail", pk=bill.pk)


@login_required
@require_tenant_role(*_CAN_MANAGE)
def bill_request_control_number(request, pk):
    """Journey C: re-requesting a control number for a bill that already
    has one returns the existing one — no new fee (Phase 4), and no new
    row here either."""
    bill = get_object_or_404(Bill, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        control_number, created = get_or_create_for_bill(
            tenant=request.tenant, bill=bill, actor=request.user
        )
        if created:
            messages.success(request, f"New control number issued: {control_number.value}")
        else:
            messages.info(request, f"Existing control number returned: {control_number.value}")
    return redirect("billing:detail", pk=bill.pk)
