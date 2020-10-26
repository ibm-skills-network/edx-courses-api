"""
URLs for edx_courses_api.
"""
from django.conf.urls import url
from django.views.generic import TemplateView

urlpatterns = [
    url(r'', TemplateView.as_view(template_name="edx_courses_api/base.html")),
]
