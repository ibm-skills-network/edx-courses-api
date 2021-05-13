"""
URLs for edx_courses_api.
"""
from django.conf import settings
from django.conf.urls import url

from .views import CourseView, hide, show, export, export_output, export_status

urlpatterns = [
    url(r'^{}/$'.format(settings.COURSE_KEY_PATTERN), CourseView.as_view(), name='course'),
    url(r'^{}/hide/$'.format(settings.COURSE_KEY_PATTERN), hide, name='hide_course'),
    url(r'^{}/show/$'.format(settings.COURSE_KEY_PATTERN), show, name='show_course'),
    url(r'^{}/export/$'.format(settings.COURSE_KEY_PATTERN), export, name='export'),
    url(r'^{}/export_status/$'.format(settings.COURSE_KEY_PATTERN), export_status, name='export_status'),
    url(r'^{}/export_output/$'.format(settings.COURSE_KEY_PATTERN), export_output, name='export_output'),
]

# Since urls.py is executed once, create service user here for server to server auth
from django.contrib.auth.models import User
try:
    User.objects.get(username=settings.AUTH_USERNAME)
except User.DoesNotExist:
    User.objects.create_user(username=settings.AUTH_USERNAME,
                                    email=settings.EMAIL,
                                    password=settings.AUTH_PASSWORD, is_staff=True)
