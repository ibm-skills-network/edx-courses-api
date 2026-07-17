"""
Tests for the ``IsServiceAccount`` permission.

These exercise the permission class in isolation (via ``RequestFactory`` and a
lightweight fake user) so they do not require importing ``views.py``, which
pulls in edx-platform modules that are not available in this standalone repo.
"""
from types import SimpleNamespace

from django.test import RequestFactory, override_settings

from edx_courses_api.permissions import IsServiceAccount


def _request(user):
    request = RequestFactory().get("/")
    request.user = user
    return request


def _user(username, is_staff=True, is_authenticated=True):
    return SimpleNamespace(
        username=username,
        is_staff=is_staff,
        is_authenticated=is_authenticated,
    )


@override_settings(AUTH_USERNAME="testservice")
def test_service_account_allowed():
    assert IsServiceAccount().has_permission(_request(_user("testservice")), None) is True


@override_settings(AUTH_USERNAME="testservice")
def test_other_username_denied():
    assert IsServiceAccount().has_permission(_request(_user("learner01")), None) is False


@override_settings(AUTH_USERNAME="testservice")
def test_matching_username_without_staff_denied():
    assert IsServiceAccount().has_permission(
        _request(_user("testservice", is_staff=False)), None
    ) is False


@override_settings(AUTH_USERNAME="testservice")
def test_unauthenticated_denied():
    assert IsServiceAccount().has_permission(
        _request(_user("testservice", is_authenticated=False)), None
    ) is False


@override_settings(AUTH_USERNAME=None)
def test_unset_auth_username_denied():
    assert IsServiceAccount().has_permission(_request(_user("testservice")), None) is False
