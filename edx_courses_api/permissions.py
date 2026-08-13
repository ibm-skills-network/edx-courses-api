from django.conf import settings
from rest_framework.permissions import BasePermission


class IsServiceAccount(BasePermission):
    """
    Allow only the dedicated Skills Network service account used for
    server-to-server calls (the configured AUTH_USERNAME) — not arbitrary
    authenticated users such as self-registered learners.
    """
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        user = request.user
        service_username = getattr(settings, "AUTH_USERNAME", None)
        return bool(
            service_username
            and user
            and user.is_authenticated
            and user.is_staff
            and user.username == service_username
        )
