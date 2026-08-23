"""Local development.

Deliberately permissive: verbose errors, no HTTPS assumptions, and the browsable
API turned on so endpoints can be poked at from a browser.
"""
from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK, config

DEBUG = True

# A bare hostname is fine locally, and Docker Compose reaches the backend by
# service name, so allow anything rather than making people edit .env.
ALLOWED_HOSTS = ['*']

# DRF's HTML browsable API is genuinely useful while building; it is left out of
# production so endpoints only ever speak JSON there.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

# Vite dev server, plus the containerised frontend.
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000,'
            'http://localhost:5173,http://127.0.0.1:5173',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()],
)
