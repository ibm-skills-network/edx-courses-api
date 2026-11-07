"""
The Open edX release the tests run against.

Each release pins its own Django: Redwood runs 4.2 and Verawood runs 5.2. So the
installed Django tells the stand-ins in mock_apps which release's signatures to
take, and tells tests/test_edx_contract.py which release's source to check them
against.
"""
import django

RELEASE = 'redwood' if django.VERSION < (5,) else 'verawood'
