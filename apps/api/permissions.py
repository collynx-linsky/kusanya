from rest_framework.permissions import BasePermission


class HasApiCredential(BasePermission):
    message = "A valid API credential is required."

    def has_permission(self, request, view):
        return bool(getattr(request, "api_credential", None))
