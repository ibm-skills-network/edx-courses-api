"""
URLs for edx_courses_api.
"""
from django.conf import settings
from django.conf.urls import url

from .views import CourseView

urlpatterns = [
    url(r'^{}'.format(settings.COURSE_KEY_PATTERN), CourseView.as_view(), name='course'),
]

# Since urls.py is executed once, create service user here for server to server auth
from django.contrib.auth.models import User
try:
    User.objects.get(username=settings.AUTH_USERNAME).delete()
except User.DoesNotExist:
    pass
User.objects.create_user(username=settings.AUTH_USERNAME, password=settings.AUTH_PASSWORD, email=settings.EMAIL, is_staff=True)
