def current_tenant(request):
    return {
        "current_tenant": getattr(request, "tenant", None),
        "current_tenant_membership": getattr(request, "tenant_membership", None),
    }
