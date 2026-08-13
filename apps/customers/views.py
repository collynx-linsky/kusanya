from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

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

    customers = Customer.objects.filter(tenant=request.tenant).prefetch_related("accounts")

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
    accounts = customer.accounts.all()
    return render(request, "customers/detail.html", {"customer": customer, "accounts": accounts})


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
def account_create(request, customer_pk):
    customer = get_object_or_404(Customer, pk=customer_pk, tenant=request.tenant)
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
            return redirect("customers:detail", pk=customer.pk)
    else:
        form = CustomerAccountForm(tenant=request.tenant)
    return render(
        request,
        "customers/form.html",
        {"form": form, "title": f"New account for {customer.full_name}"},
    )
