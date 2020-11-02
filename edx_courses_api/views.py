import base64
import logging
import os
import shutil
import tarfile
from path import Path as path
from django.core.files import File
from django.conf import settings


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import APIException
from six import text_type

# edx imports
from xmodule.contentstore.django import contentstore
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.xml_importer import import_course_from_xml
from xmodule.modulestore.django import modulestore
from cms.djangoapps.contentstore.utils import delete_course
from opaque_keys.edx.keys import CourseKey
from contentstore.storage import course_import_export_storage
from contentstore.tasks import import_olx
from openedx.core.lib.extract_tar import safetar_extractall
from django.core.exceptions import SuspiciousOperation
from djcelery.common import respect_language
from xmodule.modulestore import COURSE_ROOT

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

    def post(self, request, course_key_string):
        courselike_key = CourseKey.from_string(course_key_string)

        filename = request.FILES['course_data'].name
        if not filename.endswith('.tar.gz'):
            return Response({"developer_message": 'Parameter in the wrong format'}, status=status.HTTP_400_BAD_REQUEST)

        course_dir = path(settings.GITHUB_REPO_ROOT) / base64.urlsafe_b64encode(
            repr(course_key_string).encode('utf-8')
        ).decode('utf-8')
        temp_filepath = course_dir / filename
        if not course_dir.isdir():
            os.mkdir(course_dir)


        try:
            log.info(u'importing course to {0}'.format(temp_filepath))
            with open(temp_filepath, "wb+") as temp_file:
                for chunk in request.FILES['course_data'].chunks():
                    temp_file.write(chunk)

            tar_file = tarfile.open(temp_filepath)
            try:
                safetar_extractall(tar_file, (course_dir + u'/'))
            except SuspiciousOperation as exc:
                LOGGER.info(u'Course import %s: Unsafe tar file - %s', courselike_key, exc.args[0])
                with respect_language(language):
                    self.status.fail(_(u'Unsafe tar file. Aborting import.'))
                return
            finally:
                tar_file.close()

            log.info(u'Course import %s: Uploaded file extracted', courselike_key)

            # find the 'course.xml' file
            def get_all_files(directory):
                """
                For each file in the directory, yield a 2-tuple of (file-name,
                directory-path)
                """
                for directory_path, _dirnames, filenames in os.walk(directory):
                    for filename in filenames:
                        yield (filename, directory_path)

            def get_dir_for_filename(directory, filename):
                """
                Returns the directory path for the first file found in the directory
                with the given name.  If there is no file in the directory with
                the specified name, return None.
                """
                for name, directory_path in get_all_files(directory):
                    if name == filename:
                        return directory_path
                return None

            dirpath = get_dir_for_filename(course_dir, COURSE_ROOT)
            if not dirpath:
                with respect_language(language):
                    self.status.fail(_(u'Could not find the {0} file in the package.').format(COURSE_ROOT))
                    return

            dirpath = os.path.relpath(dirpath, path(settings.GITHUB_REPO_ROOT))
            log.debug(u'found %s at %s', COURSE_ROOT, dirpath)

            log.info(u'Course import %s: Extracted file verified', courselike_key)

            courselike_items = import_course_from_xml(
                modulestore(), ModuleStoreEnum.UserID.mgmt_command, course_dir,
                load_error_modules=False,
                static_content_store=contentstore(),
                verbose=True,
                do_import_static=False,
                create_if_not_present=True
            )

            new_location = courselike_items[0].location
            log.debug(u'new course at %s', new_location)
            log.info(u'Course import %s: Course import successful', courselike_key)
        except Exception as exception:   # pylint: disable=broad-except
            log.exception(u'error importing course', exc_info=True)
        finally:
            if course_dir.isdir():
                shutil.rmtree(course_dir)
                log.info(u'Course import %s: Temp data cleared', courselike_key)

        return Response({'status': 'done'})
