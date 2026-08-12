from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.control_numbers.models import ControlNumber


@login_required
def control_number_list(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    control_numbers = ControlNumber.objects.filter(tenant=request.tenant).select_related(
        "bill", "customer_account", "customer_account__customer"
    )
    return render(request, "control_numbers/list.html", {"control_numbers": control_numbers})
