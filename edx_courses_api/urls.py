"""
URLs for edx_courses_api.
"""
from django.conf import settings
from django.urls import re_path

from .views import CourseView, hide, show, export, export_output, export_status

urlpatterns = [
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/$', CourseView.as_view(), name='course'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/hide/$', hide, name='hide_course'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/show/$', show, name='show_course'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/export/$', export, name='export'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/export_status/$', export_status, name='export_status'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/export_output/$', export_output, name='export_output'),
]

# Since urls.py is executed once, create service user here for server to server auth
from django.contrib.auth.models import User
import logging
log = logging.getLogger(__name__)

if settings.DATABASES != None and settings.DATABASES['default'] != {}:
    try:
        User.objects.get(username=settings.AUTH_USERNAME)
    except User.DoesNotExist:
        log.info('CREATING USER WITH USERNAME {}', settings.AUTH_USERNAME)
        User.objects.create_user(username=settings.AUTH_USERNAME,
                                        email=settings.EMAIL,
                                        password=settings.AUTH_PASSWORD, is_staff=True)
