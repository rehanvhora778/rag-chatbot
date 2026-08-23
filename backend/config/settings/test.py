"""Test settings.

Optimised for a suite that runs on every push: nothing here may reach the
network, hit a real Redis, or load an ML model. Anything that would is either
disabled or pointed at an in-process stand-in, so `pytest` works on a laptop and
in CI with the same command.
"""
import tempfile
from pathlib import Path

from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK, config

DEBUG = False
ALLOWED_HOSTS = ['*']

# Long enough to satisfy the HS256 key-length check, so the suite is not run
# against a configuration the project would refuse in production — and so real
# warnings are not lost in a stream of ones the test settings caused.
# A fixed test value, never a deployed secret.
SECRET_KEY = 'test-only-key-not-used-anywhere-real-0123456789abcdef'  # noqa: S105

# ═══════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════
#
# CI runs against real PostgreSQL because pgvector and full-text search are the
# things under test and SQLite has neither. Without DATABASE_URL the suite still
# runs on SQLite, which is enough for the auth, permission and service-layer
# tests — the vector tests skip themselves.

if not config('DATABASE_URL', default=''):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }

# ═══════════════════════════════════════════════════════════════
# SPEED
# ═══════════════════════════════════════════════════════════════

# PBKDF2 with its default iteration count dominates the runtime of any suite
# that creates users. MD5 is fine here and nowhere else.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'ragchat-test',
    }
}

# No broker: tasks execute inline, in-process, and raise instead of swallowing.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Throttling makes tests order-dependent and flaky — a test that sends 21 chat
# messages would start failing the 21st for reasons unrelated to what it asserts.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {},
}

# ═══════════════════════════════════════════════════════════════
# ISOLATION
# ═══════════════════════════════════════════════════════════════

# Uploads and indexes go to a throwaway directory so a test run never touches
# the developer's real media/ or indexes/.
_TMP = Path(tempfile.mkdtemp(prefix='ragchat-test-'))
MEDIA_ROOT = _TMP / 'media'
FAISS_INDEX_DIR = _TMP / 'indexes'
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
FAISS_INDEX_DIR.mkdir(parents=True, exist_ok=True)

# Never load the real embedding model in a unit test: it is ~90 MB, wants to
# download from Hugging Face, and takes seconds per process. Tests that need
# vectors use the deterministic fake in tests/conftest.py.
EMBEDDING_PRELOAD = False

# No API key means any accidental real LLM call fails loudly instead of quietly
# spending someone's quota.
GROQ_API_KEY = ''

LOGGING['root']['level'] = 'WARNING'  # noqa: F405
