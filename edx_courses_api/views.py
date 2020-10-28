from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

# edx imports
from xmodule.modulestore import ModuleStoreEnum
from cms.djangoapps.contentstore.utils import delete_course
from opaque_keys.edx.keys import CourseKey

class CourseView(APIView):
    """
    docstring
    """
    def get(self, request, course_key_string):
        return Response({'data': 'hello world'})

    def delete(self, request, course_key_string):
        course_key = CourseKey.from_string(course_key_string)
        delete_course(course_key, ModuleStoreEnum.UserID.mgmt_command)
        return Response(status=status.HTTP_204_NO_CONTENT)
