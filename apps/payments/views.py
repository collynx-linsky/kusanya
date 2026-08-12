from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.billing.models import Bill
from apps.payments.forms import PayBillForm
from apps.payments.models import Payment
from apps.payments.services import initiate_payment, query_payment, refund_payment, reverse_payment
from apps.providers.models import PaymentProvider
from apps.tenants.models import TenantRole
from apps.tenants.permissions import require_tenant_role

_CAN_MANAGE = (TenantRole.ADMIN, TenantRole.FINANCE_MANAGER, TenantRole.BILLING_OFFICER, TenantRole.ACCOUNTANT)


@login_required
def payment_list(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    payments = Payment.objects.filter(tenant=request.tenant).select_related("control_number", "provider")
    return render(request, "payments/list.html", {"payments": payments})


@login_required
def payment_detail(request, pk):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    payment = get_object_or_404(
        Payment.objects.select_related("control_number", "control_number__bill", "provider"),
        pk=pk,
        tenant=request.tenant,
    )
    return render(request, "payments/detail.html", {"payment": payment})


@login_required
@require_tenant_role(*_CAN_MANAGE)
def pay_bill(request, bill_pk):
    bill = get_object_or_404(Bill, pk=bill_pk, tenant=request.tenant)
    control_number = getattr(bill, "control_number", None)
    if control_number is None:
        messages.error(request, "This bill has no control number yet — issue one first.")
        return redirect("billing:detail", pk=bill.pk)

    if request.method == "POST":
        form = PayBillForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            provider = PaymentProvider.objects.get(code="mock")
            payment = initiate_payment(
                tenant=request.tenant,
                control_number=control_number,
                provider=provider,
                amount=data["amount"],
                payer_reference=data["payer_reference"],
                actor=request.user,
                metadata={"mock_outcome": data["mock_outcome"]},
            )
            messages.info(request, f"Payment {payment.merchant_reference}: {payment.get_status_display()}.")
            return redirect("payments:detail", pk=payment.pk)
    else:
        form = PayBillForm(initial={"amount": bill.balance})

    return render(request, "payments/pay_bill.html", {"form": form, "bill": bill})


@login_required
@require_tenant_role(*_CAN_MANAGE)
def payment_query(request, pk):
    """Resolves an UNKNOWN payment by querying the provider — never a
    blind retry. See docs/PAYMENT_LIFECYCLE.md."""
    payment = get_object_or_404(Payment, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        query_payment(payment, actor=request.user)
        messages.info(request, f"Provider query complete. Status: {payment.get_status_display()}.")
    return redirect("payments:detail", pk=payment.pk)


@login_required
@require_tenant_role(*_CAN_MANAGE)
def payment_refund(request, pk):
    payment = get_object_or_404(Payment, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        try:
            refund_payment(payment, actor=request.user)
            messages.success(request, "Payment refunded.")
        except ValidationError as exc:
            messages.error(request, str(exc))
    return redirect("payments:detail", pk=payment.pk)


@login_required
@require_tenant_role(*_CAN_MANAGE)
def payment_reverse(request, pk):
    payment = get_object_or_404(Payment, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        try:
            reverse_payment(payment, actor=request.user)
            messages.success(request, "Payment reversed.")
        except ValidationError as exc:
            messages.error(request, str(exc))
    return redirect("payments:detail", pk=payment.pk)


@csrf_exempt
@require_POST
def mock_provider_callback(request):
    """The inbound endpoint the MOCK/SANDBOX provider calls to notify
    KUSANYA of a payment outcome. Unauthenticated by session (no tenant
    context — a provider doesn't have a KUSANYA login) and instead
    authenticated by HMAC signature, verified inside
    apps.providers.mock.MockPaymentProviderAdapter.process_callback().
    CSRF-exempt for the same reason: this is not a browser form
    submission, and signature verification is the actual protection.
    A real provider's callback endpoint would follow the identical shape
    — see docs/PAYMENT_LIFECYCLE.md and build spec section 15.
    """
    from apps.payments.models import PaymentCallbackEvent
    from apps.payments.services import process_callback

    provider = PaymentProvider.objects.filter(code="mock").first()
    if provider is None:
        return HttpResponseBadRequest("Unknown provider.")

    event = process_callback(provider=provider, raw_payload=request.body, headers=request.headers)

    if event.outcome == PaymentCallbackEvent.Outcome.INVALID_SIGNATURE:
        return HttpResponse(status=401)
    if event.outcome == PaymentCallbackEvent.Outcome.UNMATCHED:
        return HttpResponse(status=404)
    return JsonResponse({"outcome": event.outcome})
