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
User.objects.get(username='123').delete()
User.objects.create_user(username='123', password='123')
