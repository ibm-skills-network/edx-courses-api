def delete_course(course_key, user_id, keep_instructors=False):
    pass


def load_services_for_studio(runtime, user):
    pass


def reverse_course_url(handler_name, course_key, kwargs=None):
    return f'/{handler_name}/{course_key}'


def reverse_library_url(handler_name, library_key, kwargs=None):
    return f'/{handler_name}/{library_key}'
