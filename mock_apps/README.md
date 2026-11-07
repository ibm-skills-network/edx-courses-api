Stand-ins for the edx-platform and plugin modules that `edx_courses_api.views` imports.
Inside Studio the real ones are on the path. Here pytest puts this directory on
`sys.path` (`pythonpath` in tox.ini), so the views import without the platform.

Each function takes the same parameters as the real one. `tests/test_edx_contract.py`
checks that against the edx-platform source of the release under test. Tests patch
these names in `edx_courses_api.views` wherever a call's effect matters.
