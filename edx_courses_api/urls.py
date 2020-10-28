"""
URLs for edx_courses_api.
"""
from django.conf import settings
from django.conf.urls import url

from .views import CourseView

urlpatterns = [
    url(r'^{}'.format(settings.COURSE_KEY_PATTERN), CourseView.as_view(), name='course'),
]
