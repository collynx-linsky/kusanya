from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.customers.forms import CustomerAccountForm, CustomerForm
from apps.customers.models import Customer, CustomerAccount
from apps.customers.services import get_or_create_customer, get_or_create_customer_account
from apps.tenants.models import TenantRole
from apps.tenants.permissions import require_tenant_role

_CAN_MANAGE = (TenantRole.ADMIN, TenantRole.FINANCE_MANAGER, TenantRole.BILLING_OFFICER, TenantRole.ACCOUNTANT)


@login_required
def customer_list(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    customers = Customer.objects.filter(tenant=request.tenant).prefetch_related("accounts")
    return render(request, "customers/list.html", {"customers": customers})


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
