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

# On by default. This was False initially, on the reasoning that Render already
# redirects at the edge so Django doing it again adds nothing — but that
# reasoning had it backwards. A default should fail closed: the cost of it being
# on where it is redundant is one wasted redirect, while the cost of it being
# off where nothing else redirects is that the whole API answers over plain
# HTTP. Django's own deployment check flags the False case as a warning, and it
# is right to.
#
# SECURE_PROXY_SSL_HEADER above is what makes this safe behind a TLS-terminating
# proxy: without it Django would consider every forwarded request insecure and
# redirect forever. Set this to False only for a proxy that does not send
# X-Forwarded-Proto.
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)

# ═══════════════════════════════════════════════════════════════
# COOKIES
# ═══════════════════════════════════════════════════════════════

SESSION_COOKIE_SECURE   = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE      = True
CSRF_COOKIE_HTTPONLY    = False   # the admin's JS needs to read it
CSRF_COOKIE_SAMESITE    = 'Lax'
