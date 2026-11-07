"""
Tests for the edx_courses_api views, run against the stand-ins in mock_apps.
"""
import base64
import io
import json
import secrets
from unittest import mock

import pytest
import webob
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import JsonResponse
from opaque_keys.edx.keys import CourseKey, UsageKey
from rest_framework.test import APIClient

from edx_courses_api import views
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.exceptions import DuplicateCourseError

COURSE = 'course-v1:edX+DemoX+Demo_Course'
VIDEO = 'block-v1:edX+DemoX+Demo_Course+type@video+block@intro'
TRANSCRIPT_URL = f'/{COURSE}/xblock/{VIDEO}/handler/studio_transcript/translation/'
SRT = b'1\n00:00:00,000 --> 00:00:01,000\nHello\n'

pytestmark = pytest.mark.django_db


@pytest.fixture
def service_user(settings):
    return User.objects.create_user(settings.AUTH_USERNAME, password=settings.AUTH_PASSWORD, is_staff=True)


@pytest.fixture
def admin_user():
    # views.USERNAME: Studio's admin account, which owns new courses and transcript edits.
    return User.objects.create_user('admin', is_staff=True)


@pytest.fixture
def client(service_user, settings):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=_basic(settings.AUTH_USERNAME, settings.AUTH_PASSWORD))
    return client


def _basic(username, password):
    return 'Basic ' + base64.b64encode(f'{username}:{password}'.encode()).decode()


ENDPOINTS = [
    ('post', f'/{COURSE}/'),
    ('delete', f'/{COURSE}/'),
    ('post', f'/{COURSE}/hide/'),
    ('post', f'/{COURSE}/show/'),
    ('post', f'/{COURSE}/export/'),
    ('get', f'/{COURSE}/export_status/'),
    ('get', f'/{COURSE}/export_output/'),
    ('post', TRANSCRIPT_URL),
    ('delete', TRANSCRIPT_URL),
    ('post', f'/{COURSE}/certificate/settings/'),
]


@pytest.mark.parametrize('method, url', ENDPOINTS)
def test_refuses_an_account_that_is_not_the_service_account(method, url):
    learner_secret = secrets.token_hex(8)
    User.objects.create_user('learner01', password=learner_secret)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=_basic('learner01', learner_secret))
    with mock.patch.object(views, 'modulestore') as store:
        assert getattr(client, method)(url).status_code == 403
    store.assert_not_called()


# --- CourseView ---

@pytest.fixture
def course_models():
    with mock.patch.object(views.CourseMode, 'objects', create=True) as modes, \
            mock.patch.object(views.CertificateGenerationCourseSetting, 'objects', create=True) as certs, \
            mock.patch.object(views.CourseAllowPIISharingInLTIFlag, 'objects', create=True) as lti:
        yield modes, certs, lti


@pytest.mark.parametrize('sent, self_generation', [({}, True), ({'certificate_enabled': 'false'}, False)])
def test_create_course(client, admin_user, course_models, sent, self_generation):
    modes, certs, lti = course_models
    key = CourseKey.from_string(COURSE)
    with mock.patch.object(views, 'create_new_course_in_store') as create:
        create.return_value.id = key
        res = client.post(f'/{COURSE}/', {'name': 'Demo', **sent})

    assert res.status_code == 200
    create.assert_called_once_with('split', admin_user, 'edX', 'DemoX', 'Demo_Course', {'display_name': 'Demo'})
    assert [c.kwargs['mode_slug'] for c in modes.get_or_create.call_args_list] == ['audit', 'honor']
    certs.get_or_create.assert_called_once_with(course_key=key, self_generation_enabled=self_generation)
    lti.get_or_create.assert_called_once_with(course_id=key, enabled=True)


def test_create_course_that_exists(client, admin_user, course_models):
    with mock.patch.object(views, 'create_new_course_in_store', side_effect=DuplicateCourseError):
        res = client.post(f'/{COURSE}/', {'name': 'Demo'})
    assert res.status_code == 400
    assert 'already exists' in res.json()['detail']


def test_delete_course(client):
    with mock.patch.object(views, 'delete_course') as delete:
        assert client.delete(f'/{COURSE}/').status_code == 204
    delete.assert_called_once_with(CourseKey.from_string(COURSE), ModuleStoreEnum.UserID.mgmt_command)


# --- hide and show ---

@pytest.mark.parametrize('action, visibility', [('hide', 'none'), ('show', 'both')])
def test_set_catalog_visibility(client, action, visibility):
    overview = mock.Mock()
    with mock.patch.object(views.CourseOverview, 'get_from_id', return_value=overview):
        assert client.post(f'/{COURSE}/{action}/').status_code == 200
    assert overview.catalog_visibility == visibility
    overview.save.assert_called_once_with()


def test_set_catalog_visibility_of_unknown_course(client):
    # The stand-in's get_from_id raises DoesNotExist, as the real one does for an unknown key.
    assert client.post(f'/{COURSE}/hide/').status_code == 404


# --- export ---

def test_export(client, service_user):
    with mock.patch.object(views, 'modulestore') as store, mock.patch.object(views, 'export_olx') as task:
        res = client.post(f'/{COURSE}/export/', HTTP_ACCEPT_LANGUAGE='fr')
    assert res.json() == {'ExportStatus': 1}
    store.return_value.get_course.assert_called_once_with(CourseKey.from_string(COURSE))
    task.delay.assert_called_once_with(service_user.id, COURSE, 'fr')


def test_export_of_unknown_course(client):
    with mock.patch.object(views, 'modulestore') as store, mock.patch.object(views, 'export_olx') as task:
        store.return_value.get_course.return_value = None
        assert client.post(f'/{COURSE}/export/').status_code == 404
    task.delay.assert_not_called()


@pytest.fixture
def latest_task():
    task = mock.Mock(completed_steps=0)
    with mock.patch.object(views.UserTaskStatus, 'objects', create=True) as statuses:
        statuses.filter.return_value.order_by.return_value.first.return_value = task
        yield task


def test_export_status_when_done(client, latest_task):
    latest_task.state = views.UserTaskStatus.SUCCEEDED

    class Storage(views.S3Boto3Storage):
        def url(self, name):
            return f'https://bucket.example/{name}'

    artifact = mock.Mock()
    artifact.file.storage = Storage()
    artifact.file.name = 'export.tar.gz'
    with mock.patch.object(views.UserTaskArtifact, 'objects', create=True) as artifacts:
        artifacts.get.return_value = artifact
        res = client.get(f'/{COURSE}/export_status/')
    assert res.json() == {'ExportStatus': 3, 'ExportOutput': 'https://bucket.example/export.tar.gz'}


def test_export_status_when_failed(client, latest_task):
    latest_task.state = views.UserTaskStatus.FAILED
    with mock.patch.object(views.UserTaskArtifact, 'objects', create=True) as artifacts:
        artifacts.filter.return_value = [mock.Mock(text=json.dumps({'raw_error_msg': 'bad olx'}))]
        res = client.get(f'/{COURSE}/export_status/')
    assert res.json() == {'ExportStatus': -1, 'ExportError': {'raw_error_msg': 'bad olx'}}


def test_export_output(client, latest_task):
    latest_task.state = views.UserTaskStatus.SUCCEEDED
    artifact = mock.Mock()
    artifact.file.name = 'exports/demo.tar.gz'
    artifact.file.storage.size.return_value = 3
    tarball = io.BytesIO(b'tgz')
    tarball.name = 'exports/demo.tar.gz'
    with mock.patch.object(views.UserTaskArtifact, 'objects', create=True) as artifacts, \
            mock.patch.object(views, 'course_import_export_storage') as storage:
        artifacts.get.return_value = artifact
        storage.open.return_value = tarball
        res = client.get(f'/{COURSE}/export_output/')

    assert res.status_code == 200
    assert b''.join(res.streaming_content) == b'tgz'
    assert res['Content-Disposition'] == 'attachment; filename=demo.tar.gz'
    artifact.file.close.assert_called_once_with()


def test_export_output_before_the_export_finished(client, latest_task):
    latest_task.state = 'In Progress'
    assert client.get(f'/{COURSE}/export_output/').status_code == 404


# --- studio_transcript ---
#
# The view runs on two shapes of video block. The fakes copy only what the view
# touches. Redwood: edx-platform's xmodule VideoBlock answers available_translations
# itself. Verawood (built-in block and xblocks-contrib's, either way
# USE_EXTRACTED_VIDEO_BLOCK goes): the block has no available_translations, and the
# video_config service answers instead. load_services_for_studio adds that service,
# so the block cannot see it until the view has called that function.

class FakeRuntime:
    def __init__(self):
        self._services = {}
        self.modulestore = mock.Mock()

    def service(self, block, name):
        # XBlock returns None for a service a block wants but the runtime lacks.
        return self._services.get(name)


class FakeVideoBlock:
    def __init__(self, transcripts):
        self.runtime = FakeRuntime()
        self.location = UsageKey.from_string(VIDEO)
        self.edx_video_id = 'val-123'
        self.download_track = False
        self.transcripts = transcripts
        self.saved = False
        self.studio_transcript_calls = []

    def get_transcripts_info(self, is_bumper=False):
        return {'sub': '', 'transcripts': self.transcripts}

    def save(self):
        self.saved = True

    def studio_transcript(self, request, dispatch):
        # The upload is closed once the view returns, so its content is read here.
        self.studio_transcript_calls.append((request, dispatch, request.POST['file'].file.read()))
        return webob.Response(json={'edx_video_id': self.edx_video_id}, status=201)


class RedwoodVideoBlock(FakeVideoBlock):
    def available_translations(self, transcripts, verify_assets=None, is_bumper=False):
        assert verify_assets is True
        return list(transcripts['transcripts'])

    def save_with_metadata(self, user):
        raise AssertionError('the view saves through the modulestore')


class VerawoodVideoBlock(FakeVideoBlock):
    def save_with_metadata(self, user_id):
        raise AssertionError('the view saves through the modulestore')


class FakeVideoConfigService:
    def available_translations(self, video_block, transcripts, verify_assets=None, is_bumper=False):
        assert verify_assets is True
        return list(transcripts['transcripts'])


def _load_services(block_class):
    def load_services_for_studio(runtime, user):
        if block_class is VerawoodVideoBlock:
            runtime._services['video_config'] = FakeVideoConfigService()
    return load_services_for_studio


@pytest.fixture(params=[RedwoodVideoBlock, VerawoodVideoBlock], ids=['redwood-block', 'verawood-block'])
def video(request):
    """Returns a factory: video(transcripts) gives a block of this case's shape, served by a patched modulestore."""
    patches = []

    def make(transcripts):
        block = request.param(transcripts)
        store = mock.patch.object(views, 'modulestore')
        load = mock.patch.object(views, 'load_services_for_studio', side_effect=_load_services(request.param))
        block.store = store.start().return_value
        block.store.get_item.return_value = block
        block.load_services = load.start()
        patches.extend([store, load])
        return block

    yield make
    for p in patches:
        p.stop()


def _upload(client):
    return client.post(
        TRANSCRIPT_URL,
        {'file': SimpleUploadedFile('fr.srt', SRT), 'language_code': 'fr', 'new_language_code': 'fr'},
        format='multipart',
    )


def _assert_saved_and_published(block, admin_user):
    assert block.saved
    block.runtime.modulestore.update_item.assert_called_once_with(block, admin_user.id)
    block.store.publish.assert_called_once_with(block.location, admin_user.id)
    assert block.download_track is True


def test_first_transcript_goes_to_studio_upload(client, admin_user, video):
    block = video({})
    seen = {}

    def upload_transcripts(request):
        seen.update(post=request.POST.dict(), file=request.FILES['transcript-file'].read())
        return JsonResponse({'status': 'Success'})

    with mock.patch.object(views, 'upload_transcripts', side_effect=upload_transcripts):
        res = _upload(client)

    assert res.status_code == 200
    block.load_services.assert_called_once_with(block.runtime, admin_user)
    assert seen['post']['locator'] == VIDEO
    assert seen['post']['edx_video_id'] == 'val-123'
    assert seen['file'] == SRT
    assert block.studio_transcript_calls == []
    _assert_saved_and_published(block, admin_user)


def test_further_transcript_goes_to_the_block_handler(client, admin_user, video):
    block = video({'en': 'val-123-en.srt'})
    with mock.patch.object(views, 'upload_transcripts') as upload:
        res = _upload(client)

    assert res.status_code == 201
    assert res.json() == {'edx_video_id': 'val-123'}
    upload.assert_not_called()
    [(request, dispatch, content)] = block.studio_transcript_calls
    assert dispatch == 'translation'
    # The handler reads these from a webob request, the way Studio's handler URL passes them.
    assert request.method == 'POST'
    assert request.POST['edx_video_id'] == 'val-123'
    assert request.POST['new_language_code'] == 'fr'
    assert content == SRT
    _assert_saved_and_published(block, admin_user)


def test_first_transcript_without_a_file(client, admin_user, video):
    block = video({})
    with mock.patch.object(views, 'upload_transcripts') as upload:
        res = client.post(TRANSCRIPT_URL, {'language_code': 'fr'}, format='multipart')
    assert res.status_code == 400
    upload.assert_not_called()
    assert not block.saved


# --- set_certificate_settings ---

@pytest.mark.parametrize('sent, enabled', [(True, True), ('false', False), ('TRUE', True)])
def test_set_certificate_settings(client, sent, enabled):
    with mock.patch.object(views.CertificateGenerationCourseSetting, 'objects', create=True) as settings_rows:
        settings_rows.update_or_create.return_value = (mock.Mock(), True)
        res = client.post(f'/{COURSE}/certificate/settings/', {'enabled': sent}, format='json')

    assert res.json() == {'course_key': COURSE, 'enabled': enabled, 'status': 'created'}
    settings_rows.update_or_create.assert_called_once_with(
        course_key=CourseKey.from_string(COURSE), defaults={'self_generation_enabled': enabled},
    )


@pytest.mark.parametrize('body', [{}, {'enabled': 'yes'}, {'enabled': 1}])
def test_set_certificate_settings_without_a_boolean(client, body):
    with mock.patch.object(views.CertificateGenerationCourseSetting, 'objects', create=True) as settings_rows:
        res = client.post(f'/{COURSE}/certificate/settings/', body, format='json')
    assert res.status_code == 400
    settings_rows.update_or_create.assert_not_called()
