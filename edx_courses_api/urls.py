"""
URLs for edx_courses_api.
"""
from django.conf import settings
from django.urls import re_path

from .views import CourseView, hide, show, export, export_output, export_status, xblock_handler, xblock_item_handler

urlpatterns = [
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/$', CourseView.as_view(), name='course'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/xblocks/{settings.USAGE_KEY_PATTERN}?$',
            xblock_item_handler,
            name='xblock_item_handler'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/xblocks/(?P<usage_key_string>.*?)/handler/(?P<handler>[^/]*)(?:/(?P<suffix>.*))?$',
        xblock_handler,
        name='xblock_handler'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/hide/$', hide, name='hide_course'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/show/$', show, name='show_course'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/export/$', export, name='export'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/export_status/$', export_status, name='export_status'),
    re_path(fr'^{settings.COURSE_KEY_PATTERN}/export_output/$', export_output, name='export_output'),
]

# Since urls.py is executed once, create service user here for server to server auth
from django.contrib.auth.models import User
try:
    User.objects.get(username=settings.AUTH_USERNAME)
except User.DoesNotExist:
    User.objects.create_user(username=settings.AUTH_USERNAME,
                                    email=settings.EMAIL,
                                    password=settings.AUTH_PASSWORD, is_staff=True)
