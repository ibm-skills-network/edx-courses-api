import logging

from django.http.response import Http404

from rest_framework.views import APIView
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.exceptions import ParseError
from rest_framework import status
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User

# edx imports
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from cms.djangoapps.contentstore.views.course import create_new_course_in_store
from cms.djangoapps.contentstore.utils import delete_course
from xmodule.modulestore.exceptions import DuplicateCourseError
from xmodule.modulestore import ModuleStoreEnum
from opaque_keys.edx.keys import CourseKey

from course_modes.models import CourseMode
from lms.djangoapps.certificates.models import CertificateGenerationCourseSetting
from xblock_config.models import CourseEditLTIFieldsEnabledFlag


log = logging.getLogger(__name__)

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

@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def hide(request, course_key_string):
    course_key = CourseKey.from_string(course_key_string)
    log.info('setting catalog visibility for {} to "none"'.format(course_key))

    try:
        course = CourseOverview.get_from_id(course_key)
    except CourseOverview.DoesNotExist:
        raise Http404

    course.catalog_visibility = "none"
    course.save()

    return Response({'detail': "{} - catalog visibility set to 'none'".format(course_key)})

@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def show(request, course_key_string):
    course_key = CourseKey.from_string(course_key_string)
    log.info('setting catalog visibility for {} to "both"'.format(course_key))

    try:
        course = CourseOverview.get_from_id(course_key)
    except CourseOverview.DoesNotExist:
        raise Http404

    course.catalog_visibility = "both"
    course.save()

    return Response({'detail': "{} - catalog visibility set to 'both'".format(course_key)})
