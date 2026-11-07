class CourseOverview:
    class DoesNotExist(Exception):
        pass

    @classmethod
    def get_from_id(cls, course_id):
        raise cls.DoesNotExist
