"""Single source of truth for the application version.

In development this default value is used. During a tagged release build the CI
workflow (``.github/workflows/desktop-build.yml``) rewrites ``__version__`` to
match the git tag (e.g. tag ``v0.2.0`` -> ``0.2.0``) so the running desktop app
reports the exact version it was built from.
"""

__version__ = "0.1.0"
