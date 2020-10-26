"""
edx_courses_api Django application initialization.
"""

from django.apps import AppConfig


class EdxCoursesApiConfig(AppConfig):
    """
    Configuration for the edx_courses_api Django application.
    """

    name = 'edx_courses_api'
    plugin_app = {
        'url_config': {
            'lms.djangoapp': {
                'namespace': 'edx_courses_api',
                'regex': r'^sn-api/courses/',
            },
        },
        'settings_config': {
            'lms.djangoapp': {
                'common': {'relative_path': 'settings.common'},
            },
        },
    }
