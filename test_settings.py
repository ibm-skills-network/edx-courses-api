"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

from os.path import abspath, dirname, join


def root(*args):
    """
    Get the absolute path of the given path relative to the project root.
    """
    return join(abspath(dirname(__file__)), *args)


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'default.db',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
}

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'edx_courses_api',
)

# export_status reads request.session and export reads request.LANGUAGE_CODE.
# Studio's middleware sets both.
MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
]

# Copied from edx-platform's openedx/core/constants.py, which Studio's settings import.
COURSE_KEY_PATTERN = r'(?P<course_key_string>[^/+]+(/|\+)[^/+]+(/|\+)[^/?]+)'
USAGE_KEY_PATTERN = r'(?P<usage_key_string>(?:i4x://?[^/]+/[^/]+/[^/]+/[^@]+(?:@[^/]+)?)|(?:[^/]+))'
COURSE_EXPORT_DOWNLOAD_CHUNK_SIZE = 8192

LOCALE_PATHS = [
    root('edx_courses_api', 'conf', 'locale'),
]

ROOT_URLCONF = 'edx_courses_api.urls'

SECRET_KEY = 'insecure-secret-key'

AUTH_USERNAME = 'testservice'
AUTH_PASSWORD = AUTH_USERNAME
EMAIL = AUTH_USERNAME + '@skills.network'
