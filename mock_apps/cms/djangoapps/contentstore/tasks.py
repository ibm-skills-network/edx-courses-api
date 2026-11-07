class CourseExportTask:
    @classmethod
    def generate_name(cls, arguments_dict):
        return f"Export of {arguments_dict['course_key_string']}"


# A bound Celery task. Views call export_olx.delay(...) with the same arguments.
def export_olx(self, user_id, course_key_string, language):
    pass


export_olx.delay = lambda user_id, course_key_string, language: None
