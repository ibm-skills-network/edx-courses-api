import logging
import json
import logging
import os

from django.conf import settings
from django.http import Http404, StreamingHttpResponse
from wsgiref.util import FileWrapper

from rest_framework.views import APIView
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.exceptions import ParseError
from rest_framework import status
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage

# edx imports
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from cms.djangoapps.contentstore.views.course import create_new_course_in_store
from cms.djangoapps.contentstore.utils import delete_course
from xmodule.modulestore.exceptions import DuplicateCourseError
from xmodule.modulestore import ModuleStoreEnum
from opaque_keys.edx.keys import CourseKey, UsageKey
from xblock.django.request import django_to_webob_request, webob_to_django_response
from openedx.core.lib.xblock_utils import get_aside_from_xblock, is_xblock_aside
from contentstore.views.item import StudioEditModuleRuntime
from xblock.exceptions import NoSuchHandlerError
from cms.djangoapps.contentstore.views.item import _get_module_info, _get_xblock, _save_xblock

from course_modes.models import CourseMode
from lms.djangoapps.certificates.models import CertificateGenerationCourseSetting
from xblock_config.models import CourseEditLTIFieldsEnabledFlag
from xmodule.modulestore.django import modulestore
from opaque_keys.edx.locator import LibraryLocator
from storages.backends.s3boto import S3BotoStorage
from contentstore.storage import course_import_export_storage
from contentstore.tasks import CourseExportTask, CourseImportTask, export_olx, import_olx
from contentstore.utils import reverse_course_url, reverse_library_url
from user_tasks.models import UserTaskArtifact, UserTaskStatus
from user_tasks.conf import settings as user_tasks_settings

from .permissions import IsSiteAdminUser


log = logging.getLogger(__name__)
STATUS_FILTERS = user_tasks_settings.USER_TASKS_STATUS_FILTERS

USERNAME = 'admin' # the user who will be associated with new courses

class CourseView(APIView):

    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, course_key_string):
        course_key = CourseKey.from_string(course_key_string)
        log.info('DELETING {}'.format(course_key))
        delete_course(course_key, ModuleStoreEnum.UserID.mgmt_command)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def post(self, request, course_key_string):
        course_key = CourseKey.from_string(course_key_string)
        # Create the course
        try:
            user = User.objects.get(username=USERNAME)
            course_name = request.data.get("name", "Empty")
            fields = { "display_name": course_name }
            new_course = create_new_course_in_store(
                "split",
                user,
                course_key.org,
                course_key.course,
                course_key.run,
                fields
            )
            msg = u"Created {}".format(new_course.id)
            log.info(msg)
            self.finalize_course(course_key)
            return Response({'detail': msg})
        except DuplicateCourseError:
            msg = u"Course already exists for {}, {}, {}".format(course_key.org, course_key.course, course_key.run)
            log.warning(msg)
            raise ParseError(msg)


    def finalize_course(self, course_key):
        log.info('Adding honor course mode')
        CourseMode.objects.get_or_create(
            course_id=course_key,
            mode_slug=CourseMode.HONOR,
            defaults={"mode_display_name": "Honor"},
        )
        log.info('Enabling self generated certificates')
        CertificateGenerationCourseSetting.objects.get_or_create(
            course_key=course_key,
            self_generation_enabled=True,
        )
        log.info('Enabling LTI fields')
        CourseEditLTIFieldsEnabledFlag.objects.get_or_create(
            course_id=course_key,
            enabled=True
        )
        log.info('Finalized course {}'.format(str(course_key)))

def set_visibility(course_key, visibility):
    try:
        course = CourseOverview.get_from_id(course_key)
    except CourseOverview.DoesNotExist:
        raise Http404

    log.info('setting catalog visibility for {} to {}"'.format(course_key, visibility))
    course.catalog_visibility = visibility
    course.save()

@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def hide(request, course_key_string):
    course_key = CourseKey.from_string(course_key_string)
    set_visibility(course_key, "none")
    return Response({'detail': "{} - catalog visibility set to 'none'".format(course_key)})

@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def show(request, course_key_string):
    course_key = CourseKey.from_string(course_key_string)
    set_visibility(course_key, "both")
    return Response({'detail': "{} - catalog visibility set to 'both'".format(course_key)})

@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def export(request, course_key_string):
    """
    Trigger the async export job
    https://github.com/edx/edx-platform/blob/open-release/juniper.master/cms/djangoapps/contentstore/views/import_export.py#L290

    POST /sn-api/courses/<course_key>/export/
    """
    course_key = CourseKey.from_string(course_key_string)
    if isinstance(course_key, LibraryLocator):
        courselike_module = modulestore().get_library(course_key)
        context = {
            'context_library': courselike_module,
            'courselike_home_url': reverse_library_url("library_handler", course_key),
            'library': True
        }
    else:
        courselike_module = modulestore().get_course(course_key)
        if courselike_module is None:
            raise Http404
        context = {
            'context_course': courselike_module,
            'courselike_home_url': reverse_course_url("course_handler", course_key),
            'library': False
        }
    context['status_url'] = reverse_course_url('export_status_handler', course_key)

    export_olx.delay(request.user.id, course_key_string, request.LANGUAGE_CODE)
    return Response({'ExportStatus': 1})

@api_view(['GET'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def export_status(request, course_key_string, filename=None):
    """
    Get export job status
    https://github.com/edx/edx-platform/blob/open-release/juniper.master/cms/djangoapps/contentstore/views/import_export.py#L343

    GET /sn-api/courses/<course_key>/export_status/
    """
    course_key = CourseKey.from_string(course_key_string)

    # The task status record is authoritative once it's been created
    task_status = _latest_task_status(request, course_key_string, export_status)
    output_url = None
    error = None
    if task_status is None:
        # The task hasn't been initialized yet; did we store info in the session already?
        try:
            session_status = request.session["export_status"]
            status = session_status[course_key_string]
        except KeyError:
            status = 0
    elif task_status.state == UserTaskStatus.SUCCEEDED:
        status = 3
        artifact = UserTaskArtifact.objects.get(status=task_status, name='Output')
        if isinstance(artifact.file.storage, FileSystemStorage):
            output_url = reverse_course_url('export_output_handler', course_key)
        elif isinstance(artifact.file.storage, S3BotoStorage):
            filename = os.path.basename(artifact.file.name)
            disposition = u'attachment; filename="{}"'.format(filename)
            output_url = artifact.file.storage.url(artifact.file.name, response_headers={
                'response-content-disposition': disposition,
                'response-content-encoding': 'application/octet-stream',
                'response-content-type': 'application/x-tgz'
            })
        else:
            output_url = artifact.file.storage.url(artifact.file.name)
    elif task_status.state in (UserTaskStatus.FAILED, UserTaskStatus.CANCELED):
        status = max(-(task_status.completed_steps + 1), -2)
        errors = UserTaskArtifact.objects.filter(status=task_status, name='Error')
        if errors:
            error = errors[0].text
            try:
                error = json.loads(error)
            except ValueError:
                # Wasn't JSON, just use the value as a string
                pass
    else:
        status = min(task_status.completed_steps + 1, 2)

    response = {"ExportStatus": status}
    if output_url:
        response['ExportOutput'] = output_url
    elif error:
        response['ExportError'] = error

    return Response(response)

@api_view(['GET'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def export_output(request, course_key_string):
    """
    Download the exported archive
    https://github.com/edx/edx-platform/blob/open-release/juniper.master/cms/djangoapps/contentstore/views/import_export.py#L412

    GET /sn-api/courses/<course_key>/export_output/
    """
    task_status = _latest_task_status(request, course_key_string, export_output)
    if task_status and task_status.state == UserTaskStatus.SUCCEEDED:
        artifact = None
        try:
            artifact = UserTaskArtifact.objects.get(status=task_status, name='Output')
            tarball = course_import_export_storage.open(artifact.file.name)
            return send_tarball(tarball, artifact.file.storage.size(artifact.file.name))
        except UserTaskArtifact.DoesNotExist:
            raise Http404
        finally:
            if artifact:
                artifact.file.close()
    else:
        raise Http404

@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated, IsSiteAdminUser])
def xblock_handler(request, course_key_string, usage_key_string, handler, suffix=''):
    """
    Dispatch an AJAX action to an xblock

    Args:
        usage_id: The usage-id of the block to dispatch to
        handler (str): The handler to execute
        suffix (str): The remainder of the url to be passed to the handler

    Returns:
        :class:`django.http.HttpResponse`: The response from the handler, converted to a
            django response

    Example:
    POST ${STUDIO_URL}/sn-api/courses/{course_key}/xblocks/{usage_key}/handler/{handler}/

    See https://github.com/edx/edx-platform/blob/open-release/juniper.master/cms/djangoapps/contentstore/views/component.py#L449
    """
    usage_key = UsageKey.from_string(usage_key_string)

    # Let the module handle the AJAX
    req = django_to_webob_request(request)

    try:
        if is_xblock_aside(usage_key):
            # Get the descriptor for the block being wrapped by the aside (not the aside itself)
            descriptor = modulestore().get_item(usage_key.usage_key)
            handler_descriptor = get_aside_from_xblock(descriptor, usage_key.aside_type)
            asides = [handler_descriptor]
        else:
            descriptor = modulestore().get_item(usage_key)
            handler_descriptor = descriptor
            asides = []
        handler_descriptor.xmodule_runtime = StudioEditModuleRuntime(request.user)
        resp = handler_descriptor.handle(handler, req, suffix)
    except NoSuchHandlerError:
        log.info(u"XBlock %s attempted to access missing handler %r", handler_descriptor, handler, exc_info=True)
        raise Http404

    # unintentional update to handle any side effects of handle call
    # could potentially be updating actual course data or simply caching its values
    modulestore().update_item(descriptor, request.user.id, asides=asides)
    log.info('xblock content is updated (course_id: {}, xblock_id: {})'.format(course_key_string, usage_key_string))
    return webob_to_django_response(resp)

@api_view(['GET', 'POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated, IsSiteAdminUser])
def xblock_item_handler(request, course_key_string, usage_key_string):
    """
    See https://github.com/edx/edx-platform/blob/open-release/juniper.master/cms/djangoapps/contentstore/views/item.py#L104
    """
    usage_key = usage_key_with_run(usage_key_string)

    if request.method == 'GET':
        with modulestore().bulk_operations(usage_key.course_key):
            response = _get_module_info(_get_xblock(usage_key, request.user))
        return Response(response)
    elif request.method in ('PUT', 'POST'):
        return _save_xblock(
            request.user,
            _get_xblock(usage_key, request.user),
            data=request.data.get('data'),
            children_strings=request.data.get('children'),
            metadata=request.data.get('metadata'),
            nullout=request.data.get('nullout'),
            grader_type=request.data.get('graderType'),
            is_prereq=request.data.get('isPrereq'),
            prereq_usage_key=request.data.get('prereqUsageKey'),
            prereq_min_score=request.data.get('prereqMinScore'),
            prereq_min_completion=request.data.get('prereqMinCompletion'),
            publish=request.data.get('publish'),
            fields=request.data.get('fields'),
        )

def _latest_task_status(request, course_key_string, view_func=None):
    """
    Get the most recent export status update for the specified course/library
    key.
    """
    args = {u'course_key_string': course_key_string}
    name = CourseExportTask.generate_name(args)
    task_status = UserTaskStatus.objects.filter(name=name)
    for status_filter in STATUS_FILTERS:
        task_status = status_filter().filter_queryset(request, task_status, view_func)
    return task_status.order_by(u'-created').first()

def send_tarball(tarball, size):
    """
    Renders a tarball to response, for use when sending a tar.gz file to the user.
    """
    wrapper = FileWrapper(tarball, settings.COURSE_EXPORT_DOWNLOAD_CHUNK_SIZE)
    response = StreamingHttpResponse(wrapper, content_type='application/x-tgz')
    response['Content-Disposition'] = u'attachment; filename=%s' % os.path.basename(tarball.name)
    response['Content-Length'] = size
    return response

def usage_key_with_run(usage_key_string):
    """
    Converts usage_key_string to a UsageKey, adding a course run if necessary
    """
    usage_key = UsageKey.from_string(usage_key_string)
    usage_key = usage_key.replace(course_key=modulestore().fill_in_run(usage_key.course_key))
    return usage_key
