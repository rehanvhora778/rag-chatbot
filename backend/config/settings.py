import os
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

# ═══════════════════════════════════════════════════════════════
# BASE
# ═══════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-replace-me-in-production')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# Render injects the live hostname here at runtime — add it automatically so the
# service works even if ALLOWED_HOSTS wasn't set manually.
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# ═══════════════════════════════════════════════════════════════
# APPLICATIONS
# ═══════════════════════════════════════════════════════════════

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',

    # Project apps
    'apps.authentication',
    'apps.documents',
    'apps.chat',
    'apps.analytics',
    'apps.admin_panel',
]

# ═══════════════════════════════════════════════════════════════
# MIDDLEWARE
# ═══════════════════════════════════════════════════════════════

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ═══════════════════════════════════════════════════════════════
# TEMPLATES
# ═══════════════════════════════════════════════════════════════

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ═══════════════════════════════════════════════════════════════
# DATABASE — SQLite for Django internals only
# MongoDB stores all project data (documents, chats, analytics)
# ═══════════════════════════════════════════════════════════════

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ═══════════════════════════════════════════════════════════════
# MONGODB
# ═══════════════════════════════════════════════════════════════

MONGODB_HOST = config('MONGODB_HOST', default='mongodb://localhost:27017')
MONGODB_DB   = config('MONGODB_DB',   default='ragchatbot')

MONGO_COLLECTIONS = {
    'DOCUMENTS':          'documents',
    'CHUNKS':             'chunks',
    'CHAT_SESSIONS':      'chat_sessions',
    'MESSAGES':           'messages',
    'ANALYTICS':          'analytics',
    'DOCUMENT_SUMMARIES': 'document_summaries',
    'OTPS':               'otps',
}

# ═══════════════════════════════════════════════════════════════
# PASSWORD VALIDATION
# ═══════════════════════════════════════════════════════════════

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ═══════════════════════════════════════════════════════════════
# JWT
# ═══════════════════════════════════════════════════════════════

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
}

# ═══════════════════════════════════════════════════════════════
# GOOGLE (GMAIL) SIGN-IN
# ═══════════════════════════════════════════════════════════════

# OAuth 2.0 Web client ID from https://console.cloud.google.com/apis/credentials
# The same value must be given to the frontend as VITE_GOOGLE_CLIENT_ID.
# Leave blank to disable the "Continue with Google" buttons.
GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID', default='')

# Seed account used by `python manage.py create_admin`.
DEFAULT_ADMIN_EMAIL    = config('DEFAULT_ADMIN_EMAIL',    default='rehanvhora86@gmail.com')
DEFAULT_ADMIN_PASSWORD = config('DEFAULT_ADMIN_PASSWORD', default='rehan@786')
DEFAULT_ADMIN_NAME     = config('DEFAULT_ADMIN_NAME',     default='Rehan Vhora')

# ═══════════════════════════════════════════════════════════════
# EMAIL — delivers the one-time codes for sign-up and password reset
# ═══════════════════════════════════════════════════════════════

EMAIL_HOST          = config('EMAIL_HOST',     default='smtp.gmail.com')
EMAIL_PORT          = config('EMAIL_PORT',     default=587, cast=int)
EMAIL_USE_TLS       = config('EMAIL_USE_TLS',  default=True, cast=bool)
EMAIL_HOST_USER     = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_TIMEOUT       = 15                       # never hang a request on a dead SMTP host
DEFAULT_FROM_EMAIL  = config('DEFAULT_FROM_EMAIL',
                             default=EMAIL_HOST_USER or 'RAG Chatbot <no-reply@localhost>')

# Brevo's HTTP API, used when a key is present. Render's free instances have no
# outbound SMTP — smtp.gmail.com:587 fails with "[Errno 101] Network is
# unreachable" however correct the App Password is — so SMTP cannot deliver in
# production at all. HTTPS is not blocked.
BREVO_API_KEY = config('BREVO_API_KEY', default='')

# Preference order:
#   1. Brevo over HTTPS   — set BREVO_API_KEY (production)
#   2. SMTP               — set EMAIL_HOST_USER (local development)
#   3. Console            — neither set: codes are printed instead of mailed,
#                           so the OTP flow still works offline.
if BREVO_API_KEY:
    EMAIL_BACKEND = 'core.email_backends.BrevoAPIEmailBackend'
elif EMAIL_HOST_USER:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ═══════════════════════════════════════════════════════════════
# OTP — one-time codes (stored in MongoDB, never in plaintext)
# ═══════════════════════════════════════════════════════════════

OTP_LENGTH                  = 6
OTP_TTL_MINUTES             = config('OTP_TTL_MINUTES',             default=10, cast=int)
OTP_MAX_ATTEMPTS            = config('OTP_MAX_ATTEMPTS',            default=5,  cast=int)
OTP_RESEND_COOLDOWN_SECONDS = config('OTP_RESEND_COOLDOWN_SECONDS', default=60, cast=int)
OTP_MAX_SENDS_PER_HOUR      = config('OTP_MAX_SENDS_PER_HOUR',      default=6,  cast=int)
# How long the ticket handed out after a correct reset code stays usable.
OTP_RESET_TOKEN_TTL_MINUTES = config('OTP_RESET_TOKEN_TTL_MINUTES', default=15, cast=int)

# ═══════════════════════════════════════════════════════════════
# DJANGO REST FRAMEWORK
# ═══════════════════════════════════════════════════════════════

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # Only views that set `throttle_scope` are throttled (e.g. the RAG chat
    # endpoint). Keyed per-user for authenticated requests. Tune via env.
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'chat': config('CHAT_THROTTLE_RATE', default='20/min'),
    },
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
}

# ═══════════════════════════════════════════════════════════════
# CORS
# ═══════════════════════════════════════════════════════════════

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000',
    cast=Csv(),
)
# Needed for the Django admin login (and any cross-site POST) over HTTPS in prod.
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://*.onrender.com',
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization',
    'content-type', 'dnt', 'origin', 'user-agent',
    'x-csrftoken', 'x-requested-with',
]
# Let the browser read the smart PDF filename from the download response.
CORS_EXPOSE_HEADERS = ['Content-Disposition']

# ═══════════════════════════════════════════════════════════════
# FILE STORAGE
# ═══════════════════════════════════════════════════════════════

MEDIA_URL  = '/media/'
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# On Railway, VOLUME_PATH points to the persistent disk mount
_VOLUME = Path(os.environ.get('VOLUME_PATH', str(BASE_DIR)))
MEDIA_ROOT = _VOLUME / 'media'

DATA_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024
# Uploads above this stream to a temp file instead of being buffered in RAM.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

MAX_DOCUMENT_SIZE_MB = config('MAX_DOCUMENT_SIZE_MB', default=50, cast=int)

ALLOWED_DOCUMENT_EXTENSIONS = ['pdf', 'docx', 'txt']
ALLOWED_DOCUMENT_MIME_TYPES = [
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
]

# --- PDF processing speed knobs ---
# Table detection (PyMuPDF find_tables) runs a costly layout analysis on EVERY
# page. It's off by default because it dominates extraction time on large PDFs;
# enable it only for table-heavy documents.
PDF_EXTRACT_TABLES = config('PDF_EXTRACT_TABLES', default=False, cast=bool)
# Scanned/image pages are OCR'd via Groq Vision (one network call per page).
# These calls run in parallel with this many workers to avoid serial waiting.
OCR_MAX_WORKERS = config('OCR_MAX_WORKERS', default=6, cast=int)

# ═══════════════════════════════════════════════════════════════
# FAISS
# ═══════════════════════════════════════════════════════════════

FAISS_INDEX_DIR = _VOLUME / 'indexes'
FAISS_INDEX_DIR.mkdir(exist_ok=True)
MEDIA_ROOT.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# EMBEDDINGS
# ═══════════════════════════════════════════════════════════════

EMBEDDING_MODEL_NAME = config('EMBEDDING_MODEL_NAME', default='all-MiniLM-L6-v2')
EMBEDDING_DIMENSION  = 384
# Larger batches cut Python overhead when embedding many chunks on CPU.
EMBEDDING_BATCH_SIZE = config('EMBEDDING_BATCH_SIZE', default=64, cast=int)

# Backend: 'onnx' (ONNX Runtime — uses the DirectML GPU when available, several
# times faster than torch on CPU too) or 'torch' (original sentence-transformers).
# Both produce identical vectors, so switching never invalidates FAISS indexes.
EMBEDDING_BACKEND       = config('EMBEDDING_BACKEND',       default='onnx')
# ONNX provider: 'auto' (DirectML if present, else CPU), 'dml', or 'cpu'.
EMBEDDING_ONNX_PROVIDER = config('EMBEDDING_ONNX_PROVIDER', default='auto')
# Load the model in the background at server start (first upload doesn't wait).
EMBEDDING_PRELOAD       = config('EMBEDDING_PRELOAD',       default=True, cast=bool)

# ═══════════════════════════════════════════════════════════════
# GROQ LLM
# ═══════════════════════════════════════════════════════════════

GROQ_API_KEY           = config('GROQ_API_KEY', default='')
GROQ_MODEL             = config('GROQ_MODEL', default='llama-3.3-70b-versatile')
# Reads images: OCR for scanned PDF pages that have no selectable text.
# Groq retired the llama-4 vision models this was originally built against; check
# https://console.groq.com/docs/models before changing it, as most Groq models are
# text-only and reject image input outright.
GROQ_VISION_MODEL      = config('GROQ_VISION_MODEL', default='qwen/qwen3.6-27b')
GROQ_MAX_OUTPUT_TOKENS = config('GROQ_MAX_OUTPUT_TOKENS', default=2048, cast=int)
GROQ_TEMPERATURE       = config('GROQ_TEMPERATURE', default=0.2, cast=float)

# ═══════════════════════════════════════════════════════════════
# RAG PIPELINE
# ═══════════════════════════════════════════════════════════════

# Chunking is CHARACTER-based (see services/chunker.py).
RAG_CHUNK_SIZE           = config('RAG_CHUNK_SIZE',           default=900,  cast=int)
RAG_CHUNK_OVERLAP        = config('RAG_CHUNK_OVERLAP',        default=200,  cast=int)

# Retrieval: pull a wide candidate pool (fetch_k) then MMR-select top_k.
RAG_TOP_K                = config('RAG_TOP_K',                default=6,    cast=int)
RAG_FETCH_K              = config('RAG_FETCH_K',              default=24,   cast=int)
RAG_USE_MMR              = config('RAG_USE_MMR',              default=True, cast=bool)
RAG_MMR_LAMBDA           = config('RAG_MMR_LAMBDA',           default=0.7,  cast=float)

# Low floor only — the grounding prompt is the real relevance judge.
RAG_MIN_SIMILARITY_SCORE = config('RAG_MIN_SIMILARITY_SCORE', default=0.2,  cast=float)

# When True, the chat API returns retrieved-chunk diagnostics (page/score/preview).
RAG_DEBUG                = config('RAG_DEBUG',                default=False, cast=bool)

CONVERSATION_MEMORY_TURNS = config('CONVERSATION_MEMORY_TURNS', default=5,  cast=int)

# ═══════════════════════════════════════════════════════════════
# INTERNATIONALISATION
# ═══════════════════════════════════════════════════════════════

LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'UTC'
USE_I18N = True
USE_TZ   = True

# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] [{levelname}] [{name}] {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'app_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'app.log'),
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'errors.log'),
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'level': 'ERROR',
        },
    },
    'root': {
        'handlers': ['console', 'app_file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'app_file'],
            'level': config('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'app_file', 'error_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'core': {
            'handlers': ['console', 'app_file', 'error_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'services': {
            'handlers': ['console', 'app_file', 'error_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

# ═══════════════════════════════════════════════════════════════
# SECURITY HARDENING (production)
# ═══════════════════════════════════════════════════════════════

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER      = True
    SECURE_CONTENT_TYPE_NOSNIFF    = True
    X_FRAME_OPTIONS                = 'DENY'
    SECURE_HSTS_SECONDS            = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD            = True
    SESSION_COOKIE_SECURE          = True
    CSRF_COOKIE_SECURE             = True
