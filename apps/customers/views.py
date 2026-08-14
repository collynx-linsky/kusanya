from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.audit.services import get_activity_for, record_audit_event
from apps.core.encrypted_fields import compute_lookup_hash
from apps.customers.forms import CustomerAccountForm, CustomerForm
from apps.customers.models import Customer, CustomerAccount
from apps.customers.services import get_or_create_customer, get_or_create_customer_account
from apps.tenants.models import TenantRole
from apps.tenants.permissions import require_tenant_role

_CAN_MANAGE = (TenantRole.ADMIN, TenantRole.FINANCE_MANAGER, TenantRole.BILLING_OFFICER, TenantRole.ACCOUNTANT)

# full_name/email/phone_number are encrypted at rest (ADR-032) — search
# on them can only be exact-match via their lookup_hash companions, the
# same constraint already applied to Django admin search
# (apps.customers.admin.CustomerAdmin). external_reference is plain, so
# it still supports a real substring match.
_SORTABLE_FIELDS = {
    "created_at": "created_at",
    "-created_at": "-created_at",
    "is_active": "is_active",
    "-is_active": "-is_active",
}


@login_required
def customer_list(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")

    # annotate(account_count=...), not prefetch_related("accounts") +
    # {{ customer.accounts.count }} in the template -- .count() on a
    # related manager always issues its own query regardless of
    # prefetching (prefetch only helps .all()/iteration), so the
    # original version ran one extra COUNT query per row on every page
    # of the list (up to 25/page). See ARCHITECTURE_DECISIONS ADR-039.
    customers = Customer.objects.filter(tenant=request.tenant).annotate(account_count=Count("accounts"))

    query = request.GET.get("q", "").strip()
    if query:
        customers = customers.filter(
            Q(external_reference__icontains=query)
            | Q(full_name_lookup_hash=compute_lookup_hash(query))
            | Q(email_lookup_hash=compute_lookup_hash(query.lower()))
            | Q(phone_number_lookup_hash=compute_lookup_hash(query))
        )

    sort = request.GET.get("sort", "-created_at")
    customers = customers.order_by(_SORTABLE_FIELDS.get(sort, "-created_at"))

    paginator = Paginator(customers, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "customers": page_obj.object_list,
        "query": query,
        "sort": sort,
        "customer_create_url": reverse("customers:create"),
    }
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "kz-customer-table":
        return render(request, "customers/_table.html", context)
    return render(request, "customers/list.html", context)


@login_required
def customer_detail(request, pk):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    customer = get_object_or_404(Customer, pk=pk, tenant=request.tenant)
    # Same reasoning as customer_list above -- annotate, don't call
    # .bills.count() per row in the template.
    accounts = customer.accounts.annotate(bill_count=Count("bills"))
    activity = get_activity_for(customer)
    return render(
        request, "customers/detail.html", {"customer": customer, "accounts": accounts, "activity": activity}
    )


@login_required
@require_tenant_role(*_CAN_MANAGE)
def customer_create(request):
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            customer, created = get_or_create_customer(
                tenant=request.tenant,
                full_name=data["full_name"],
                email=data["email"],
                phone_number=data["phone_number"],
                external_reference=data["external_reference"],
                actor=request.user,
            )
            if created:
                messages.success(request, f"Customer '{customer.full_name}' created.")
            else:
                messages.info(request, "A customer with this reference already exists.")
            return redirect("customers:detail", pk=customer.pk)
    else:
        form = CustomerForm()
    return render(request, "customers/form.html", {"form": form, "title": "New customer"})


@login_required
@require_tenant_role(*_CAN_MANAGE)
def customer_edit(request, pk):
    customer = get_object_or_404(Customer, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        before = {
            "full_name": customer.full_name,
            "email": customer.email,
            "phone_number": customer.phone_number,
            "external_reference": customer.external_reference,
        }
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            after = {
                "full_name": customer.full_name,
                "email": customer.email,
                "phone_number": customer.phone_number,
                "external_reference": customer.external_reference,
            }
            record_audit_event(
                action="customer.updated", actor=request.user, tenant=request.tenant,
                target=customer, before=before, after=after,
            )
            messages.success(request, f"Customer '{customer.full_name}' updated.")
            return redirect("customers:detail", pk=customer.pk)
    else:
        form = CustomerForm(instance=customer)
    return render(request, "customers/form.html", {"form": form, "title": f"Edit {customer.full_name}"})


@login_required
@require_tenant_role(*_CAN_MANAGE)
def customer_deactivate(request, pk):
    """Deactivation, not deletion — a Customer with bills/payments
    attached can never be hard-deleted without corrupting financial
    history (same principle as every other domain model here); `is_active`
    is the correct "remove from active use" analog, already on the model."""
    customer = get_object_or_404(Customer, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        customer.is_active = False
        customer.save(update_fields=["is_active", "updated_at"])
        record_audit_event(
            action="customer.deactivated", actor=request.user, tenant=request.tenant, target=customer,
        )
        messages.success(request, f"'{customer.full_name}' deactivated.")
    return redirect("customers:detail", pk=customer.pk)


@login_required
@require_tenant_role(*_CAN_MANAGE)
def customer_activate(request, pk):
    customer = get_object_or_404(Customer, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        customer.is_active = True
        customer.save(update_fields=["is_active", "updated_at"])
        record_audit_event(
            action="customer.reactivated", actor=request.user, tenant=request.tenant, target=customer,
        )
        messages.success(request, f"'{customer.full_name}' reactivated.")
    return redirect("customers:detail", pk=customer.pk)


@login_required
@require_tenant_role(*_CAN_MANAGE)
def customer_bulk_deactivate(request):
    """Real bulk operation, not client-side-only checkbox theater — each
    selected customer gets an individual audit event (same as a
    one-at-a-time deactivate), so the activity timeline stays complete
    regardless of which path was used. See docs/DESIGN_SYSTEM.md's
    "Bulk operations" section."""
    if request.method == "POST":
        ids = request.POST.getlist("customer_ids")
        customers = Customer.objects.filter(pk__in=ids, tenant=request.tenant, is_active=True)
        count = 0
        for customer in customers:
            customer.is_active = False
            customer.save(update_fields=["is_active", "updated_at"])
            record_audit_event(
                action="customer.deactivated", actor=request.user, tenant=request.tenant, target=customer,
                metadata={"bulk": True},
            )
            count += 1
        if count:
            messages.success(request, f"{count} customer{'s' if count != 1 else ''} deactivated.")
        else:
            messages.info(request, "No customers were selected.")
    return redirect("customers:list")


@login_required
@require_tenant_role(*_CAN_MANAGE)
def account_create(request, customer_pk):
    """Reference implementation of the HTMX-loaded-modal pattern
    (docs/DESIGN_SYSTEM.md) — the customer detail page's "New account"
    button loads this view's GET response straight into the shared
    #kzModal shell instead of a full page navigation. Progressive
    enhancement: a direct (non-HTMX) request to this same URL still
    renders a complete standalone page, so the feature works with
    HTMX/JS unavailable too — nothing here is modal-only functionality.
    """
    customer = get_object_or_404(Customer, pk=customer_pk, tenant=request.tenant)
    is_htmx = request.headers.get("HX-Request") == "true"

    if request.method == "POST":
        form = CustomerAccountForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            data = form.cleaned_data
            account, created = get_or_create_customer_account(
                tenant=request.tenant,
                customer=customer,
                name=data["name"],
                revenue_source=data["revenue_source"],
                external_reference=data["external_reference"],
                actor=request.user,
            )
            if created:
                messages.success(request, f"Account '{account.name}' created.")
            else:
                messages.info(request, "An account with this reference already exists.")
            response = redirect("customers:detail", pk=customer.pk)
            if is_htmx:
                # A plain 302 would make htmx AJAX-fetch the target and
                # swap it into #kzModalBody -- HX-Redirect instead tells
                # htmx to perform a real browser navigation, which is
                # what "form succeeded, now show the updated page" means
                # here (the modal closes because the page reloads).
                response["HX-Redirect"] = response.url
            return response
        elif is_htmx:
            # Validation failed inside the modal -- re-render just the
            # form fragment with errors, don't navigate anywhere.
            return render(
                request,
                "customers/_account_form_modal.html",
                {"form": form, "customer": customer},
            )
    else:
        form = CustomerAccountForm(tenant=request.tenant)

    if is_htmx:
        return render(request, "customers/_account_form_modal.html", {"form": form, "customer": customer})
    return render(
        request,
        "customers/form.html",
        {"form": form, "title": f"New account for {customer.full_name}"},
    )
