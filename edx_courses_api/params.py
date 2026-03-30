"""
Request parameter parsing that does not depend on edx-platform, so it can be tested on its own.
"""

TRUE_STRINGS = ('true', '1', 'yes', 'on')
FALSE_STRINGS = ('false', '0', 'no', 'off')


def parse_bool(value):
    """
    Return True or False for a JSON boolean or a string such as "true" or "false".

    Return None for anything else, so the caller can tell a bad value from a missing one.
    glados has sent both JSON booleans and strings for these flags.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in TRUE_STRINGS:
            return True
        if lowered in FALSE_STRINGS:
            return False
    return None


def first_present(data, keys):
    """
    Return the value of the first key in keys that data has, or None.

    A JSON body can be a list, a string or a number. `in` on a string matches substrings,
    and on a number it raises TypeError, so anything that is not a dict counts as no keys.
    DRF's form QueryDict is a dict subclass and still works.
    """
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data:
            return data[key]
    return None
