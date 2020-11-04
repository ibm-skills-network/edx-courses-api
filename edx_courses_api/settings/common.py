"""
See apps.py for details on how this sort of plugin configures itself for
integration with Open edX.
"""

import os

def plugin_settings(settings):
    """
    Modify the provided settings object with settings specific to this plugin.
    """
    settings.AUTH_USERNAME = os.environ.get('AUTH_USERNAME')
    settings.AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD')
    if not settings.AUTH_USERNAME or not settings.AUTH_PASSWORD:
        raise Exception('AUTH_USERNAME or AUTH_PASSWORD environment variables not set')
