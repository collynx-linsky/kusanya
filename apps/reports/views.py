"""
Reporting. See build spec section 27.

Not a generic report-builder engine — a focused set of views over the
domain models that already exist, each with the filters build spec
section 27 names (date, status, customer, revenue source, channel/
provider where applicable) and CSV export. Reconciliation runs and
settlement batches are themselves already reports
(apps.reconciliation.views, apps.settlement.views) and aren't duplicated
here — see docs/REPORTING.md for the full picture of where each report
in section 27's list actually lives.
"""

from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum
from django.shortcuts import render

from apps.audit.models import AuditLog
from apps.billing.models import Bill
from apps.payments.models import Payment
from apps.reports.csv_export import render_csv


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@login_required
def reports_index(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    return render(request, "reports/index.html")


@login_required
def bills_report(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")

    bills = Bill.objects.filter(tenant=request.tenant).select_related("customer_account", "revenue_source")

    status = request.GET.get("status", "")
    if status:
        bills = bills.filter(status=status)
    date_from = _parse_date(request.GET.get("date_from"))
    if date_from:
        bills = bills.filter(created_at__date__gte=date_from)
    date_to = _parse_date(request.GET.get("date_to"))
    if date_to:
        bills = bills.filter(created_at__date__lte=date_to)

    bills = bills.order_by("-created_at")

    if request.GET.get("format") == "csv":
        return render_csv(
            "bills.csv",
            ["Bill number", "Customer account", "Status", "Total", "Currency", "Created"],
            (
                [b.bill_number, b.customer_account.name, b.status, b.total_amount, b.currency, b.created_at]
                for b in bills
            ),
        )

    total = bills.aggregate(total=Sum("total_amount"))["total"] or 0
    return render(
        request,
        "reports/bills.html",
        {"bills": bills[:500], "total": total, "status_choices": Bill._meta.get_field("status").choices},
    )


@login_required
def payments_report(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")

    payments = Payment.objects.filter(tenant=request.tenant).select_related("provider", "channel", "control_number")

    status = request.GET.get("status", "")
    if status:
        payments = payments.filter(status=status)
    date_from = _parse_date(request.GET.get("date_from"))
    if date_from:
        payments = payments.filter(initiated_at__date__gte=date_from)
    date_to = _parse_date(request.GET.get("date_to"))
    if date_to:
        payments = payments.filter(initiated_at__date__lte=date_to)

    payments = payments.order_by("-initiated_at")

    if request.GET.get("format") == "csv":
        return render_csv(
            "payments.csv",
            ["Reference", "Control number", "Status", "Amount", "Currency", "Provider", "Initiated"],
            (
                [
                    p.merchant_reference, p.control_number.value, p.status, p.amount, p.currency,
                    p.provider.code, p.initiated_at,
                ]
                for p in payments
            ),
        )

    total_amount = payments.aggregate(total=Sum("amount"))["total"] or 0
    return render(
        request,
        "reports/payments.html",
        {"payments": payments[:500], "total_amount": total_amount, "status_choices": Payment._meta.get_field("status").choices},
    )


@login_required
def collections_report(request):
    """Gross collections + platform revenue for a period — build spec
    section 27's "collections" report."""
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")

    from apps.payments.models import PaymentStatus
    from apps.revenue.models import RevenueEvent

    payments = Payment.objects.filter(tenant=request.tenant, status=PaymentStatus.SUCCESSFUL)
    date_from = _parse_date(request.GET.get("date_from"))
    if date_from:
        payments = payments.filter(completed_at__date__gte=date_from)
    date_to = _parse_date(request.GET.get("date_to"))
    if date_to:
        payments = payments.filter(completed_at__date__lte=date_to)

    gross = payments.aggregate(total=Sum("amount"))["total"] or 0

    revenue_events = RevenueEvent.objects.filter(tenant=request.tenant)
    if date_from:
        revenue_events = revenue_events.filter(created_at__date__gte=date_from)
    if date_to:
        revenue_events = revenue_events.filter(created_at__date__lte=date_to)
    platform_revenue = revenue_events.aggregate(total=Sum("amount"))["total"] or 0

    return render(
        request,
        "reports/collections.html",
        {
            "payment_count": payments.count(),
            "gross": gross,
            "platform_revenue": platform_revenue,
            "net_to_institution": gross,  # KUSANYA's fee is charged separately, not deducted — see docs/MONEY_FLOW.md
        },
    )


@login_required
def outstanding_balances_report(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")

    from apps.billing.models import BillStatus

    bills = (
        Bill.objects.filter(tenant=request.tenant, status__in=[BillStatus.ACTIVE, BillStatus.PARTIALLY_PAID])
        .select_related("customer_account")
        .order_by("-created_at")
    )
    rows = [(b, b.balance) for b in bills if b.balance > 0]
    total_outstanding = sum((balance for _, balance in rows), 0)

    if request.GET.get("format") == "csv":
        return render_csv(
            "outstanding_balances.csv",
            ["Bill number", "Customer account", "Total", "Balance", "Currency"],
            ([b.bill_number, b.customer_account.name, b.total_amount, balance, b.currency] for b, balance in rows),
        )

    return render(
        request, "reports/outstanding_balances.html", {"rows": rows, "total_outstanding": total_outstanding}
    )


@login_required
def audit_report(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")

    events = AuditLog.objects.filter(tenant=request.tenant).select_related("actor").order_by("-created_at")

    action = request.GET.get("action", "")
    if action:
        events = events.filter(action__icontains=action)
    date_from = _parse_date(request.GET.get("date_from"))
    if date_from:
        events = events.filter(created_at__date__gte=date_from)
    date_to = _parse_date(request.GET.get("date_to"))
    if date_to:
        events = events.filter(created_at__date__lte=date_to)

    if request.GET.get("format") == "csv":
        return render_csv(
            "audit_events.csv",
            ["Date", "Action", "Actor", "Correlation ID"],
            ([e.created_at, e.action, e.actor_label or "system", e.correlation_id] for e in events),
        )

    paginator = Paginator(events, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {"page_obj": page_obj, "events": page_obj.object_list, "action": action}
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "kz-audit-table":
        return render(request, "reports/_audit_table.html", context)
    return render(request, "reports/audit.html", context)
