from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.notifications.models import Notification


@login_required
def notification_list(request):
    if request.tenant is None:
        return render(request, "dashboard/no_access.html")
    notifications = Notification.objects.filter(tenant=request.tenant)[:200]
    return render(request, "notifications/list.html", {"notifications": notifications})
