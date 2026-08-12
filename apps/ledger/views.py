from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.ledger.models import LedgerEntry


@login_required
def ledger_list(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    entries = LedgerEntry.objects.filter(tenant=request.tenant).select_related("content_type")
    entry_type = request.GET.get("entry_type")
    if entry_type:
        entries = entries.filter(entry_type=entry_type)
    return render(
        request,
        "ledger/list.html",
        {"entries": entries[:200], "entry_types": LedgerEntry._meta.get_field("entry_type").choices},
    )
