from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from apps.receipts.models import Receipt


@login_required
def receipt_list(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    receipts = Receipt.objects.filter(tenant=request.tenant)[:200]
    return render(request, "receipts/list.html", {"receipts": receipts})


@login_required
def receipt_detail(request, pk):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    receipt = get_object_or_404(Receipt, pk=pk, tenant=request.tenant)
    return render(request, "receipts/detail.html", {"receipt": receipt})
