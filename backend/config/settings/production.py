"""Production.

Refuses to start on a misconfiguration rather than starting insecurely — a
silently-weak production deployment is worse than one that fails loudly at boot.
"""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, SECRET_KEY, config

DEBUG = False

# ═══════════════════════════════════════════════════════════════
# FAIL-FAST CONFIGURATION CHECKS
# ═══════════════════════════════════════════════════════════════
#
# base.py gives SECRET_KEY a development default so `manage.py` works out of the
# box. That default reaching production would make every JWT and session cookie
# forgeable by anyone who has read this repository, so it is rejected here.

if not SECRET_KEY or SECRET_KEY.startswith('django-insecure'):
    raise ImproperlyConfigured(
        'SECRET_KEY must be set to a strong random value in production. '
        'The development default is not usable here.'
    )

if not ALLOWED_HOSTS or ALLOWED_HOSTS == ['localhost', '127.0.0.1']:
    raise ImproperlyConfigured(
        'ALLOWED_HOSTS must name the real hostname(s) this service answers on.'
    )

# ═══════════════════════════════════════════════════════════════
# HTTPS / TRANSPORT
# ═══════════════════════════════════════════════════════════════

SECURE_BROWSER_XSS_FILTER      = True
SECURE_CONTENT_TYPE_NOSNIFF    = True
X_FRAME_OPTIONS                = 'DENY'
SECURE_REFERRER_POLICY         = 'strict-origin-when-cross-origin'

SECURE_HSTS_SECONDS            = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD            = True

# Render, Railway and every other PaaS terminate TLS at a proxy and forward
# plain HTTP. Without this header Django believes every request is insecure,
# and any redirect-to-HTTPS would loop forever.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Off by default: Render already redirects HTTP to HTTPS at the edge, so turning
# this on adds nothing there but does add a way for a proxy that forwards the
# header incorrectly to produce an infinite redirect. Turn it on when Django is
# the first thing the client actually reaches.
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)

# ═══════════════════════════════════════════════════════════════
# COOKIES
# ═══════════════════════════════════════════════════════════════

SESSION_COOKIE_SECURE   = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE      = True
CSRF_COOKIE_HTTPONLY    = False   # the admin's JS needs to read it
CSRF_COOKIE_SAMESITE    = 'Lax'
