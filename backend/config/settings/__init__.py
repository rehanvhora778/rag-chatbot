"""Environment-aware settings dispatch.

Everything in the project points at ``config.settings`` (manage.py, wsgi.py,
asgi.py, build.sh, render.yaml). Rather than change all of those — and break
every deployment that already sets ``DJANGO_SETTINGS_MODULE`` — this package
keeps that name working and picks the right module underneath.

Selection order:

1. ``DJANGO_ENV`` if set — ``development`` | ``production`` | ``test``.
2. Otherwise inferred from ``DEBUG``: ``DEBUG=False`` means production.
   Render already sets ``DEBUG=False`` and nothing else, so the existing
   deployment lands on production.py without any config change.
3. Otherwise development.

Pointing ``DJANGO_SETTINGS_MODULE`` straight at a submodule
(``config.settings.production``) also works and skips this dispatch entirely.
"""
import os

_explicit = os.environ.get('DJANGO_SETTINGS_MODULE', '')

# Only dispatch when something asked for the package itself. If the caller named
# a submodule directly, Django reads that module and this indirection would just
# import a second settings module for nothing.
if _explicit in ('', 'config.settings'):
    _env = os.environ.get('DJANGO_ENV', '').strip().lower()

    if not _env:
        _debug = os.environ.get('DEBUG', '').strip().lower()
        _env = 'production' if _debug in ('false', '0', 'no', 'off') else 'development'

    if _env == 'production':
        from .production import *  # noqa: F401,F403
    elif _env == 'test':
        from .test import *  # noqa: F401,F403
    else:
        from .development import *  # noqa: F401,F403
