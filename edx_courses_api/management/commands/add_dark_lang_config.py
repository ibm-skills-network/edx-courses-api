"""
Management command for adding Dark Lang config.
"""


import logging

from django.core.management.base import BaseCommand


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Add Dark Lang config.
    """
    help = "Add Dark Lang config."

    def add_arguments(self, parser):
        parser.add_argument('--langs',
                            action='store',
                            dest='langs',
                            default='',
                            help='A comma seperated list of supported language codes.')


    def handle(self, *args, **options):
        langs = options['langs']
        logger.info(f"Enabling support for {langs}")
