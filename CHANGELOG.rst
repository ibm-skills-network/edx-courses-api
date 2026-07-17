Change Log
----------

..
   All enhancements and patches to edx_courses_api will be documented
   in this file.  It adheres to the structure of https://keepachangelog.com/ ,
   but in reStructuredText instead of Markdown (for ease of incorporation into
   Sphinx documentation and the PyPI description).
   
   This project adheres to Semantic Versioning (https://semver.org/).

.. There should always be an "Unreleased" section for changes pending release.

Unreleased
~~~~~~~~~~

*

[0.5.2] - 2026-07-17
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Fixed
_____

* Restrict all course endpoints to the dedicated service account
  (``AUTH_USERNAME``) via a new ``IsServiceAccount`` permission, instead of
  allowing any authenticated user (missing authorization / CWE-862).

[0.1.0] - 2020-10-26
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Added
_____

* First release on PyPI.
