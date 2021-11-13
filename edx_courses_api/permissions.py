from rest_framework.permissions import IsAuthenticated, BasePermission

class IsSiteAdminUser(BasePermission):
    """
    Allow access to only site admins if in multisite mode or staff or superuser
    if in standalone mode
    """

    def has_permission(self, request, view):
        return is_site_admin_user(request)

def is_active_staff_or_superuser(user):
    """
    Checks if user is active staff or superuser.
    """
    return user and user.is_active and (user.is_staff or user.is_superuser)

def is_site_admin_user(request):
    """
    Determines if the requesting user has access to site admin data
    """
    if not request.user.is_active:
        return False

    if is_active_staff_or_superuser(request.user):
        return True

