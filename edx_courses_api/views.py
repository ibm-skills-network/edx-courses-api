import base64
import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated

# edx imports
from xmodule.modulestore import ModuleStoreEnum
from cms.djangoapps.contentstore.utils import delete_course
from opaque_keys.edx.keys import CourseKey

log = logging.getLogger(__name__)

class CourseView(APIView):

    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, course_key_string):
        return Response({'data': 'hello worlds'})

    def delete(self, request, course_key_string):
        course_key = CourseKey.from_string(course_key_string)
        log.info('DELETING {}'.format(course_key))
        delete_course(course_key, ModuleStoreEnum.UserID.mgmt_command)
        return Response(status=status.HTTP_204_NO_CONTENT)
