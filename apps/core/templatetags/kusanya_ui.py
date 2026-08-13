"""Template tags/filters backing the design system (docs/DESIGN_SYSTEM.md).
Deliberately small and generic — these back reusable *markup* patterns
(active-nav-link, status badges, pagination query strings), not
page-specific logic, which stays in each view."""

from django import template
from django.utils.http import urlencode

register = template.Library()

# Best-effort status -> Bootstrap semantic color mapping, based on common
# vocabulary across KUSANYA's various status fields (PaymentStatus,
# TenantStatus, NotificationStatus, ReconciliationException.status,
# SettlementStatus, WebhookDelivery.status, ...). Deliberately a single
# shared heuristic rather than one badge template per model — status
# values across the domain already share this vocabulary by convention
# (see docs/PRODUCT_REQUIREMENTS.md's universal data model). A status
# not covered here just renders as neutral, never breaks.
_STATUS_COLOR = {
    "success": {"active", "completed", "sent", "successful", "paid", "confirmed", "resolved", "delivered"},
    "warning": {"pending", "open", "partial", "initiated", "processing", "unknown"},
    "danger": {"failed", "rejected", "suspended", "reversed", "cancelled", "dead_letter", "expired"},
    "info": {"refunded", "settled"},
}


@register.simple_tag(takes_context=True)
def is_active_ns(context, *namespaces: str) -> str:
    """Renders "active" if the current view's URL namespace is one of the
    given names — for highlighting the current section in the sidebar."""
    request = context.get("request")
    if request is None or not getattr(request, "resolver_match", None):
        return ""
    return "active" if request.resolver_match.app_name in namespaces else ""


@register.simple_tag(takes_context=True)
def is_active_view(context, *view_names: str) -> str:
    """Like is_active_ns, but matches a specific "app:url_name" rather
    than a whole namespace -- for nav links that share a namespace with
    other pages (e.g. core:background-jobs vs. core:dashboard-router)
    and would otherwise both highlight together."""
    request = context.get("request")
    if request is None or not getattr(request, "resolver_match", None):
        return ""
    return "active" if request.resolver_match.view_name in view_names else ""


@register.filter
def status_badge_class(value) -> str:
    """`{{ payment.status|status_badge_class }}` -> a Bootstrap
    `text-bg-*` class. Falls back to "secondary" for anything not in the
    heuristic above — never raises, never leaves a badge unstyled."""
    key = str(value).strip().lower()
    for color, values in _STATUS_COLOR.items():
        if key in values:
            return f"text-bg-{color}"
    return "text-bg-secondary"


@register.simple_tag(takes_context=True)
def querystring_with(context, **overrides) -> str:
    """`{% querystring_with page=3 %}` -> the current query string with
    the given keys overridden, everything else (search, filters, sort)
    preserved — the building block for pagination/sort links that don't
    clobber each other."""
    request = context.get("request")
    params = request.GET.copy() if request is not None else {}
    for key, value in overrides.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = urlencode(params, doseq=True)
    return f"?{encoded}" if encoded else "?"
